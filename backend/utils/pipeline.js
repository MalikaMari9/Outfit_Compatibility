import { spawn } from "child_process";
import fs from "fs/promises";
import path from "path";
import {
  BACKEND_CACHE_DIR,
  PIPELINE_CONFIG_PATH,
  PIPELINE_SCRIPTS_DIR,
  PROJECT_ROOT,
  ensureDir,
} from "./paths.js";

const PYTHON_BIN = String(process.env.PYTHON_BIN || "python").trim() || "python";
const PIPELINE_TIMEOUT_MS = Math.max(30_000, Number(process.env.PIPELINE_TIMEOUT_MS || 300_000));
const RECOMMEND_TIMEOUT_MS = Math.max(60_000, Number(process.env.RECOMMEND_TIMEOUT_MS || 900_000));
const DEFAULT_RECOMMEND_TOP_K = 3;
const DEFAULT_RECOMMEND_SHORTLIST_K = 25;

const toBool = (value, fallback = false) => {
  if (value === undefined || value === null) return fallback;
  const norm = String(value).trim().toLowerCase();
  if (!norm) return fallback;
  if (["1", "true", "yes", "on"].includes(norm)) return true;
  if (["0", "false", "no", "off"].includes(norm)) return false;
  return fallback;
};

const makeJsonOutPath = (prefix) => {
  ensureDir(BACKEND_CACHE_DIR);
  const stamp = Date.now();
  const rand = Math.random().toString(16).slice(2, 10);
  return path.resolve(BACKEND_CACHE_DIR, `${prefix}_${stamp}_${rand}.json`);
};

const resolveBgMethod = (raw) => {
  const value = String(raw || "").trim().toLowerCase();
  if (!value) return "";
  const allowed = new Set(["none", "rembg", "u2net", "u2netp", "isnet", "segformer"]);
  return allowed.has(value) ? value : "";
};

const runPython = (args, timeoutMs = PIPELINE_TIMEOUT_MS) =>
  new Promise((resolve, reject) => {
    const child = spawn(PYTHON_BIN, args, {
      cwd: PROJECT_ROOT,
      windowsHide: true,
    });

    let stdout = "";
    let stderr = "";
    let timedOut = false;

    const timer = setTimeout(() => {
      timedOut = true;
      child.kill("SIGTERM");
    }, timeoutMs);

    child.stdout.on("data", (buf) => {
      stdout += String(buf);
    });

    child.stderr.on("data", (buf) => {
      stderr += String(buf);
    });

    child.on("error", (err) => {
      clearTimeout(timer);
      reject(err);
    });

    child.on("close", (code) => {
      clearTimeout(timer);
      if (timedOut) {
        return reject(
          new Error(`Pipeline process timed out after ${timeoutMs} ms`),
        );
      }
      if (code !== 0) {
        return reject(
          new Error(
            `Pipeline process failed (code=${code}). stderr=${stderr.trim()} stdout=${stdout.trim()}`,
          ),
        );
      }
      return resolve({ stdout, stderr });
    });
  });

const runPipelineScript = async ({ scriptName, scriptArgs, outPrefix, timeoutMs = PIPELINE_TIMEOUT_MS }) => {
  const scriptPath = path.resolve(PIPELINE_SCRIPTS_DIR, scriptName);
  const jsonOutPath = makeJsonOutPath(outPrefix);
  const args = [
    scriptPath,
    ...scriptArgs,
    "--config",
    PIPELINE_CONFIG_PATH,
    "--json-out",
    jsonOutPath,
    "--public-output",
  ];

  try {
    await runPython(args, timeoutMs);
    const raw = await fs.readFile(jsonOutPath, "utf-8");
    return JSON.parse(raw);
  } finally {
    await fs.unlink(jsonOutPath).catch(() => {});
  }
};

const clampInt = (value, fallback, min, max) => {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return fallback;
  const rounded = Math.round(parsed);
  return Math.max(min, Math.min(max, rounded));
};

export const runPairCompatibility = async ({
  topImagePath,
  bottomImagePath,
  bgMethod,
  deferLlm = false,
}) => {
  const args = ["--top-image", topImagePath, "--bottom-image", bottomImagePath];
  const resolvedBg = resolveBgMethod(bgMethod);
  if (resolvedBg) {
    args.push("--bg-method", resolvedBg);
  }
  if (deferLlm) {
    args.push("--defer-llm");
  }
  return runPipelineScript({
    scriptName: "run_pair.py",
    scriptArgs: args,
    outPrefix: "pair",
  });
};

export const runRecommendation = async ({
  imagePath,
  topK = DEFAULT_RECOMMEND_TOP_K,
  shortlistK = DEFAULT_RECOMMEND_SHORTLIST_K,
  forceMode = "",
  bgMethod,
  deferLlm = false,
  fastMode = false,
}) => {
  const safeTopK = clampInt(topK, DEFAULT_RECOMMEND_TOP_K, 1, 20);
  const safeShortlistK = clampInt(shortlistK, DEFAULT_RECOMMEND_SHORTLIST_K, 10, 400);
  const args = [
    "--image",
    imagePath,
    "--top-k",
    String(safeTopK),
    "--shortlist-k",
    String(safeShortlistK),
  ];
  const normalizedMode = String(forceMode || "").trim().toLowerCase();
  if (normalizedMode === "top2bottom" || normalizedMode === "bottom2top") {
    args.push("--mode", normalizedMode);
  }
  const resolvedBg = resolveBgMethod(bgMethod);
  if (resolvedBg) {
    args.push("--bg-method", resolvedBg);
  }
  if (deferLlm) {
    args.push("--defer-llm");
  }
  if (toBool(fastMode, false)) {
    args.push("--fast");
  }
  return runPipelineScript({
    scriptName: "run_recommend.py",
    scriptArgs: args,
    outPrefix: "recommend",
    timeoutMs: RECOMMEND_TIMEOUT_MS,
  });
};

export const runHybridRecommendation = async ({
  imagePath,
  wardrobeItems = [],
  topK = DEFAULT_RECOMMEND_TOP_K,
  shortlistK = DEFAULT_RECOMMEND_SHORTLIST_K,
  forceMode = "",
  bgMethod,
  deferLlm = false,
  fastMode = false,
  allowPolyvoreFallback = true,
}) => {
  const safeTopK = clampInt(topK, DEFAULT_RECOMMEND_TOP_K, 1, 20);
  const safeShortlistK = clampInt(shortlistK, DEFAULT_RECOMMEND_SHORTLIST_K, 10, 400);
  const wardrobePath = makeJsonOutPath("recommend_wardrobe");
  await fs.writeFile(wardrobePath, JSON.stringify(Array.isArray(wardrobeItems) ? wardrobeItems : []), "utf-8");
  try {
    const args = [
      "--image",
      imagePath,
      "--wardrobe-json",
      wardrobePath,
      "--top-k",
      String(safeTopK),
      "--shortlist-k",
      String(safeShortlistK),
    ];
    const normalizedMode = String(forceMode || "").trim().toLowerCase();
    if (normalizedMode === "top2bottom" || normalizedMode === "bottom2top") {
      args.push("--mode", normalizedMode);
    }
    const resolvedBg = resolveBgMethod(bgMethod);
    if (resolvedBg) {
      args.push("--bg-method", resolvedBg);
    }
    if (deferLlm) {
      args.push("--defer-llm");
    }
    if (toBool(fastMode, false)) {
      args.push("--fast");
    }
    if (!toBool(allowPolyvoreFallback, true)) {
      args.push("--disable-polyvore-fallback");
    }
    return await runPipelineScript({
      scriptName: "run_recommend_hybrid.py",
      scriptArgs: args,
      outPrefix: "recommend_hybrid",
      timeoutMs: RECOMMEND_TIMEOUT_MS,
    });
  } finally {
    await fs.unlink(wardrobePath).catch(() => {});
  }
};

export const runOllamaExplanation = async ({ facts }) => {
  const factsPath = makeJsonOutPath("explain_facts");
  await fs.writeFile(factsPath, JSON.stringify(facts), "utf-8");
  try {
    return await runPipelineScript({
      scriptName: "run_explain.py",
      scriptArgs: ["--facts-json", factsPath],
      outPrefix: "explain",
    });
  } finally {
    await fs.unlink(factsPath).catch(() => {});
  }
};

export const runWardrobeFeatureExtraction = async ({
  imagePath,
  semantic,
  bgMethod,
}) => {
  const args = ["--image", imagePath];
  const semanticRaw = String(semantic || "").trim().toLowerCase();
  if (semanticRaw) {
    args.push("--semantic", semanticRaw);
  }
  const resolvedBg = resolveBgMethod(bgMethod);
  if (resolvedBg) {
    args.push("--bg-method", resolvedBg);
  }
  return runPipelineScript({
    scriptName: "run_extract_item_features.py",
    scriptArgs: args,
    outPrefix: "wardrobe_features",
    timeoutMs: PIPELINE_TIMEOUT_MS,
  });
};
