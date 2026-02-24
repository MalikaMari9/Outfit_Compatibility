import { extractUploadedFilePaths, removeFiles } from "../utils/img.js";
import path from "path";
import clothing from "../models/clothing.js";
import { verifyToken } from "../utils/jwt.js";
import { UPLOADS_PERSISTENT_DIR } from "../utils/paths.js";
import {
  runHybridRecommendation,
  runOllamaExplanation,
  runPairCompatibility,
  runRecommendation,
} from "../utils/pipeline.js";

const isDebugRequested = (req) => {
  const raw = req?.body?.debug;
  if (raw === undefined || raw === null) return false;
  const normalized = String(raw).trim().toLowerCase();
  return normalized === "1" || normalized === "true" || normalized === "yes" || normalized === "on";
};

const asRecord = (value) => {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  return { ...value };
};

const sanitizeAutocrop = (details, key) => {
  const row = asRecord(details[key]);
  if (Object.keys(row).length === 0) return;
  delete row.processed_path;
  details[key] = row;
};

const sanitizeDetailsForClient = (details, debugEnabled) => {
  const safe = asRecord(details);
  sanitizeAutocrop(safe, "top_autocrop");
  sanitizeAutocrop(safe, "bottom_autocrop");
  sanitizeAutocrop(safe, "query_autocrop");
  sanitizeAutocrop(safe, "candidate_autocrop");
  if (!debugEnabled) {
    delete safe.debug_trace;
    delete safe.llm_raw;
    delete safe.llm_error;
  }
  return safe;
};

const sanitizePipelinePayload = (payload, debugEnabled) => {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return payload;
  const safe = { ...payload };
  if (!debugEnabled) {
    delete safe.debug_trace;
  }
  if (safe.details && typeof safe.details === "object" && !Array.isArray(safe.details)) {
    safe.details = sanitizeDetailsForClient(safe.details, debugEnabled);
  }
  if (Array.isArray(safe.results)) {
    safe.results = safe.results.map((row) => {
      if (!row || typeof row !== "object" || Array.isArray(row)) return row;
      const next = { ...row };
      if (next.details && typeof next.details === "object" && !Array.isArray(next.details)) {
        next.details = sanitizeDetailsForClient(next.details, debugEnabled);
      }
      return next;
    });
  }
  return safe;
};

const sanitizeExplainPayload = (payload, debugEnabled) => {
  const raw = asRecord(payload);
  const hasExplanation =
    raw.llm_explanation && typeof raw.llm_explanation === "object" && !Array.isArray(raw.llm_explanation);
  const status = String(raw.llm_status || "unavailable").toLowerCase();
  const sourceRaw = String(raw.llm_source || "").trim().toLowerCase();
  const source = sourceRaw || (status === "fallback" ? "fallback" : hasExplanation ? "ollama" : "none");
  const publicStatus = hasExplanation
    ? source === "fallback" || status === "fallback"
      ? "fallback"
      : "ok"
    : status === "deferred"
      ? "deferred"
      : "unavailable";
  const safe = {
    llm_status: publicStatus,
    llm_cached: Boolean(raw.llm_cached || false),
    llm_source: source,
  };
  if (hasExplanation) {
    safe.llm_explanation = raw.llm_explanation;
  }
  if (debugEnabled) {
    if (typeof raw.llm_raw === "string" && raw.llm_raw.trim()) {
      safe.llm_raw = raw.llm_raw;
    }
    if (raw.llm_error !== undefined && raw.llm_error !== null && String(raw.llm_error).trim()) {
      safe.llm_error = String(raw.llm_error);
    }
  }
  return safe;
};

const pushTrace = (trace, stage, message, meta = undefined) => {
  const row = {
    ts: new Date().toISOString(),
    stage: String(stage || ""),
    message: String(message || ""),
  };
  if (meta !== undefined) {
    row.meta = meta;
  }
  trace.push(row);
};

const attachTrace = (payload, trace, enabled) => {
  if (!enabled) return payload;
  if (payload && typeof payload === "object") {
    if (payload.details && typeof payload.details === "object" && !Array.isArray(payload.details)) {
      payload.details.debug_trace = trace;
      return payload;
    }
    payload.debug_trace = trace;
    return payload;
  }
  return { payload, debug_trace: trace };
};

const fileForField = (files, field) => {
  if (!files || typeof files !== "object") return null;
  const slot = files[field];
  if (!Array.isArray(slot) || slot.length === 0) return null;
  return slot[0] || null;
};

const toBool = (value, fallback = false) => {
  if (value === undefined || value === null) return fallback;
  const norm = String(value).trim().toLowerCase();
  if (!norm) return fallback;
  if (["1", "true", "yes", "on"].includes(norm)) return true;
  if (["0", "false", "no", "off"].includes(norm)) return false;
  return fallback;
};

const normalizeForceMode = (value) => {
  const norm = String(value || "").trim().toLowerCase();
  if (norm === "top2bottom" || norm === "bottom2top") return norm;
  return "";
};

const normalizePairInputMode = (value) => {
  const norm = String(value || "").trim().toLowerCase();
  if (norm === "full_body" || norm === "fullbody" || norm === "full_body_auto_split") return "full_body";
  return "two_piece";
};

const normalizeWardrobeSemantic = (value) => {
  const raw = String(value || "").trim().toLowerCase();
  if (raw === "top" || raw === "tops") return "tops";
  if (raw === "bottom" || raw === "bottoms") return "bottoms";
  return "";
};

const toWardrobeCandidate = (row) => {
  if (!row || typeof row !== "object") return null;
  const imageUrl = String(row.imagePath || "").trim();
  const fileName = path.basename(imageUrl);
  const semantic = normalizeWardrobeSemantic(row?.details?.category || row?.details?.semantic);
  if (!fileName || !semantic) return null;
  const features =
    row?.details?.features && typeof row.details.features === "object" && !Array.isArray(row.details.features)
      ? row.details.features
      : null;
  const wardrobeName = String(row?.details?.name || row?.details?.description || "").trim();
  const fallbackName = path.parse(fileName).name || "Untitled Item";
  return {
    item_id: String(row._id || fileName),
    category: semantic,
    image_url: imageUrl,
    local_path: path.resolve(UPLOADS_PERSISTENT_DIR, fileName),
    features,
    name: wardrobeName || fallbackName,
  };
};

export const compatibilityCheck = async (req, res) => {
  const debugEnabled = isDebugRequested(req);
  const debugTrace = [];
  const tempPaths = extractUploadedFilePaths(req);
  pushTrace(debugTrace, "request_received", "Compatibility request received.", {
    debug: debugEnabled,
    uploaded_file_count: tempPaths.length,
  });
  try {
    const decoded = await verifyToken(req.headers?.authorization);
    if (!decoded?.id) {
      pushTrace(debugTrace, "auth_error", "Unauthorized compatibility request.");
      const payload = {
        message: "Session expired. Please log in again.",
        code: "SESSION_EXPIRED",
      };
      return res.status(401).json(attachTrace(payload, debugTrace, debugEnabled));
    }

    const requestedInputMode = normalizePairInputMode(req.body?.input_mode);
    const topFile = fileForField(req.files, "top");
    const bottomFile = fileForField(req.files, "bottom");
    const fullBodyFile = fileForField(req.files, "full_body");
    const inputMode =
      requestedInputMode === "full_body" || (fullBodyFile && !topFile && !bottomFile)
        ? "full_body"
        : "two_piece";
    pushTrace(debugTrace, "input_validation", "Validating compatibility input files.", {
      input_mode: inputMode,
      requested_input_mode: requestedInputMode,
      has_top: Boolean(topFile?.path),
      has_bottom: Boolean(bottomFile?.path),
      has_full_body: Boolean(fullBodyFile?.path),
    });

    let topImagePath = "";
    let bottomImagePath = "";
    if (inputMode === "full_body") {
      if (!fullBodyFile?.path) {
        const payload = {
          message: "Please upload one image under `full_body` for full-body mode.",
        };
        pushTrace(debugTrace, "input_error", "Missing required full-body image.");
        return res.status(400).json(attachTrace(payload, debugTrace, debugEnabled));
      }
      topImagePath = String(fullBodyFile.path);
      bottomImagePath = String(fullBodyFile.path);
    } else {
      if (!topFile?.path || !bottomFile?.path) {
        const payload = {
          message: "Please upload both `top` and `bottom` image files.",
        };
        pushTrace(debugTrace, "input_error", "Missing one or more required top/bottom files.");
        return res.status(400).json(attachTrace(payload, debugTrace, debugEnabled));
      }
      topImagePath = String(topFile.path);
      bottomImagePath = String(bottomFile.path);
    }

    pushTrace(debugTrace, "pipeline_start", "Running pair compatibility pipeline.");
    const payload = await runPairCompatibility({
      topImagePath,
      bottomImagePath,
      bgMethod: req.body?.bg_method,
      deferLlm: true,
    });

    if (payload && typeof payload === "object") {
      if (!payload.details || typeof payload.details !== "object" || Array.isArray(payload.details)) {
        payload.details = {};
      }
      payload.details.input_mode = inputMode === "full_body" ? "full_body_auto_split" : "two_piece";
      payload.details.llm_status = String(payload.details.llm_status || "deferred");
      payload.details.llm_cached = Boolean(payload.details.llm_cached || false);

      if (inputMode === "full_body") {
        const topReason = String(payload.details?.top_autocrop?.reason || "").trim().toLowerCase();
        const bottomReason = String(payload.details?.bottom_autocrop?.reason || "").trim().toLowerCase();
        const splitOk = topReason === "ok" && bottomReason === "ok";
        payload.details.split_status = splitOk ? "ok" : "failed";
        payload.details.split_gate = {
          required_top_reason: "ok",
          required_bottom_reason: "ok",
          top_reason: topReason || "unknown",
          bottom_reason: bottomReason || "unknown",
        };
        if (!splitOk) {
          pushTrace(debugTrace, "split_gate_failed", "Full-body split gate rejected this image.", {
            top_reason: topReason || "unknown",
            bottom_reason: bottomReason || "unknown",
          });
          const failPayload = sanitizePipelinePayload(
            {
              message:
                "Full-body auto split could not confidently isolate both top and bottom. Please upload separate top and bottom images.",
              code: "FULL_BODY_SPLIT_FAILED",
              details: payload.details,
            },
            debugEnabled,
          );
          return res.status(422).json(attachTrace(failPayload, debugTrace, debugEnabled));
        }
      } else {
        payload.details.split_status = "not_applicable";
      }
    }
    pushTrace(debugTrace, "pipeline_success", "Pair compatibility pipeline completed.", {
      label: payload?.label,
      final_score: payload?.final_score,
      input_mode: inputMode,
    });
    const safePayload = sanitizePipelinePayload(payload, debugEnabled);
    return res.status(200).json(attachTrace(safePayload, debugTrace, debugEnabled));
  } catch (err) {
    console.error("compatibilityCheck error:", err);
    pushTrace(debugTrace, "pipeline_error", "Pair compatibility pipeline failed.", {
      error: String(err?.message || err),
    });
    const payload = {
      message: "Compatibility request failed.",
      error: String(err?.message || err),
    };
    return res.status(500).json(attachTrace(payload, debugTrace, debugEnabled));
  } finally {
    pushTrace(debugTrace, "cleanup", "Cleaning up temporary uploaded files.", {
      temp_file_count: tempPaths.length,
    });
    await removeFiles(tempPaths);
  }
};

export const recommendOutfit = async (req, res) => {
  const debugEnabled = isDebugRequested(req);
  const debugTrace = [];
  const tempPaths = extractUploadedFilePaths(req);
  pushTrace(debugTrace, "request_received", "Recommendation request received.", {
    debug: debugEnabled,
    uploaded_file_count: tempPaths.length,
  });
  try {
    const file = req.file;
    const fastMode = toBool(req.body?.fast_mode, true);
    const includePolyvore = toBool(req.body?.include_polyvore, true);
    const forceMode = normalizeForceMode(req.body?.force_mode);
    const requestedTopK = Number(req.body?.top_k);
    const requestedShortlistK = Number(req.body?.shortlist_k);
    const safeTopK = Number.isFinite(requestedTopK) ? Math.max(1, Math.min(20, Math.round(requestedTopK))) : 3;
    const safeShortlistK = Number.isFinite(requestedShortlistK)
      ? Math.max(10, Math.min(400, Math.round(requestedShortlistK)))
      : 25;
    pushTrace(debugTrace, "input_validation", "Validating uploaded image.", {
      has_image: Boolean(file?.path),
      fast_mode: fastMode,
      include_polyvore: includePolyvore,
      force_mode: forceMode || "auto",
    });
    if (!file?.path) {
      const payload = {
        message: "Please upload one image under field `image`.",
      };
      pushTrace(debugTrace, "input_error", "Missing required image file.");
      return res.status(400).json(attachTrace(payload, debugTrace, debugEnabled));
    }

    const decoded = await verifyToken(req.headers?.authorization);
    if (!decoded?.id) {
      pushTrace(debugTrace, "auth_error", "Unauthorized recommendation request.");
      const payload = {
        message: "Session expired. Please log in again.",
        code: "SESSION_EXPIRED",
      };
      return res.status(401).json(attachTrace(payload, debugTrace, debugEnabled));
    }

    let wardrobeCandidates = [];
    try {
      const wardrobeItems = await clothing.find({ userId: decoded.id }).sort({ createdAt: -1 }).lean();
      wardrobeCandidates = wardrobeItems.map(toWardrobeCandidate).filter(Boolean);
      pushTrace(debugTrace, "wardrobe_candidates", "Prepared wardrobe candidates for hybrid recommend.", {
        count: wardrobeCandidates.length,
      });
    } catch (wardrobeErr) {
      const wardrobeError = String(wardrobeErr?.message || wardrobeErr);
      pushTrace(debugTrace, "wardrobe_candidates_error", "Failed to read wardrobe candidates.", {
        error: wardrobeError,
      });
      const payload = {
        message: "Unable to read wardrobe items right now. Please retry.",
        error: wardrobeError,
        code: "WARDROBE_READ_FAILED",
      };
      return res.status(503).json(attachTrace(payload, debugTrace, debugEnabled));
    }

    const useHybrid = wardrobeCandidates.length > 0;
    pushTrace(
      debugTrace,
      "pipeline_start",
      useHybrid
        ? includePolyvore
          ? "Running hybrid recommendation pipeline (wardrobe + Polyvore fallback)."
          : "Running hybrid recommendation pipeline (wardrobe-only mode)."
        : includePolyvore
          ? "Running catalog recommendation pipeline."
          : "Wardrobe-only mode active with no wardrobe candidates; returning empty recommendation set.",
      {
        hybrid: useHybrid,
        include_polyvore: includePolyvore,
      },
    );

    const payload = useHybrid
      ? await runHybridRecommendation({
          imagePath: String(file.path),
          wardrobeItems: wardrobeCandidates,
          topK: req.body?.top_k,
          shortlistK: req.body?.shortlist_k,
          forceMode,
          bgMethod: req.body?.bg_method,
          deferLlm: true,
          fastMode,
          allowPolyvoreFallback: includePolyvore,
        })
      : includePolyvore
        ? await runRecommendation({
            imagePath: String(file.path),
            topK: req.body?.top_k,
            shortlistK: req.body?.shortlist_k,
            forceMode,
            bgMethod: req.body?.bg_method,
            deferLlm: true,
            fastMode,
          })
        : {
            message: "No matching items found in your wardrobe. You can request external recommendations.",
            recommendation_scope: "wardrobe_only",
            query_image: path.basename(String(file.path)),
            mode: "wardrobe_only",
            top_k: safeTopK,
            shortlist_k: safeShortlistK,
            fast_mode: fastMode,
            semantic_detection: {
              semantic: "unknown",
              source: "backend_guard",
              category: "",
              confidence: 0,
              reason: "no_wardrobe_candidates",
            },
            quality_gate: {
              fallback_triggered: false,
              fallback_reason: "no_wardrobe_candidates",
            },
            source_mix: {
              wardrobe_count: 0,
              polyvore_count: 0,
            },
            fallback_policy: {
              allow_polyvore_fallback: false,
              polyvore_fallback_used: false,
            },
            results: [],
          };
    if (payload && typeof payload === "object" && Array.isArray(payload.results) && payload.results.length > 0) {
      const first = payload.results[0];
      if (first && typeof first === "object" && first.details && typeof first.details === "object") {
        first.details.llm_status = String(first.details.llm_status || "deferred");
        first.details.llm_cached = Boolean(first.details.llm_cached || false);
      }
    }
    pushTrace(debugTrace, "pipeline_success", "Recommendation pipeline completed.", {
      mode: payload?.mode,
      result_count: Array.isArray(payload?.results) ? payload.results.length : 0,
    });
    const safePayload = sanitizePipelinePayload(payload, debugEnabled);
    return res.status(200).json(attachTrace(safePayload, debugTrace, debugEnabled));
  } catch (err) {
    console.error("recommendOutfit error:", err);
    const errMsg = String(err?.message || err);
    pushTrace(debugTrace, "pipeline_error", "Recommendation pipeline failed.", {
      error: errMsg,
    });
    if (errMsg.toLowerCase().includes("timed out")) {
      const payload = {
        message:
          "Recommendation is taking longer than expected (likely first-run cache warmup). Please retry in 1-2 minutes.",
        error: errMsg,
        code: "RECOMMEND_TIMEOUT",
      };
      return res.status(503).json(attachTrace(payload, debugTrace, debugEnabled));
    }
    const payload = {
      message: "Recommendation request failed.",
      error: errMsg,
    };
    return res.status(500).json(attachTrace(payload, debugTrace, debugEnabled));
  } finally {
    pushTrace(debugTrace, "cleanup", "Cleaning up temporary uploaded files.", {
      temp_file_count: tempPaths.length,
    });
    await removeFiles(tempPaths);
  }
};

export const explainFromFacts = async (req, res) => {
  const debugEnabled = isDebugRequested(req);
  const decoded = await verifyToken(req.headers?.authorization);
  if (!decoded?.id) {
    return res.status(401).json({
      message: "Session expired. Please log in again.",
      code: "SESSION_EXPIRED",
      llm_status: "unavailable",
      llm_cached: false,
    });
  }
  const facts = req?.body?.facts;
  if (!facts || typeof facts !== "object" || Array.isArray(facts)) {
    return res.status(400).json({
      message: "Please provide `facts` object in request body.",
    });
  }

  try {
    const payload = await runOllamaExplanation({ facts });
    return res.status(200).json(sanitizeExplainPayload(payload, debugEnabled));
  } catch (err) {
    console.error("explainFromFacts error:", err);
    return res.status(500).json({
      message: "Explanation request failed.",
      error: String(err?.message || err),
      llm_status: "unavailable",
      llm_cached: false,
    });
  }
};
