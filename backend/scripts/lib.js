import fs from "fs";
import path from "path";
import mongoose from "mongoose";

import user from "../models/user.js";
import clothing from "../models/clothing.js";
import feedbackReport from "../models/feedbackReport.js";
import { RUNTIME_DIR, UPLOADS_PERSISTENT_DIR } from "../utils/paths.js";
import { resolveDbConfig } from "../utils/dbTarget.js";

const COLLECTIONS = [
  { key: "user", fileName: "user.json", model: user },
  { key: "clothing", fileName: "clothing.json", model: clothing },
  { key: "feedback_report", fileName: "feedback_report.json", model: feedbackReport },
];

export const BACKUP_ROOT_DIR = path.resolve(RUNTIME_DIR, "backups");
export const DB_BACKUP_ROOT_DIR = path.resolve(BACKUP_ROOT_DIR, "db");
export const UPLOADS_BACKUP_ROOT_DIR = path.resolve(BACKUP_ROOT_DIR, "uploads");

export const parseArgs = (argv = process.argv.slice(2)) => {
  const parsed = {};
  for (const rawArg of argv) {
    if (!String(rawArg).startsWith("--")) continue;
    const trimmed = String(rawArg).slice(2);
    const eqIdx = trimmed.indexOf("=");
    if (eqIdx === -1) {
      parsed[trimmed] = true;
      continue;
    }
    parsed[trimmed.slice(0, eqIdx)] = trimmed.slice(eqIdx + 1);
  }
  return parsed;
};

export const parseBool = (value, fallback = false) => {
  if (value === undefined || value === null || value === "") return fallback;
  const normalized = String(value).trim().toLowerCase();
  if (["1", "true", "yes", "on"].includes(normalized)) return true;
  if (["0", "false", "no", "off"].includes(normalized)) return false;
  return fallback;
};

export const ensureDir = (dirPath) => {
  fs.mkdirSync(dirPath, { recursive: true });
  return dirPath;
};

export const createTimestamp = () => new Date().toISOString().replace(/[:.]/g, "-");

export const listBackupDirs = (rootDir) => {
  if (!fs.existsSync(rootDir)) return [];
  return fs
    .readdirSync(rootDir, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => path.resolve(rootDir, entry.name))
    .sort((a, b) => path.basename(b).localeCompare(path.basename(a)));
};

export const findLatestBackupDir = (rootDir) => {
  const dirs = listBackupDirs(rootDir);
  return dirs.length > 0 ? dirs[0] : "";
};

export const disconnectDb = async () => {
  if (mongoose.connection.readyState !== 0) {
    await mongoose.disconnect();
  }
};

export const connectToTarget = async (target) => {
  const resolved = resolveDbConfig(target);
  await mongoose.connect(resolved.uri);
  return resolved;
};

const writeJson = (filePath, payload) => {
  fs.writeFileSync(filePath, JSON.stringify(payload, null, 2), "utf8");
};

const copyDirectoryRecursive = (sourceDir, targetDir) => {
  ensureDir(targetDir);
  const entries = fs.readdirSync(sourceDir, { withFileTypes: true });
  for (const entry of entries) {
    const src = path.resolve(sourceDir, entry.name);
    const dst = path.resolve(targetDir, entry.name);
    if (entry.isDirectory()) {
      copyDirectoryRecursive(src, dst);
      continue;
    }
    fs.copyFileSync(src, dst);
  }
};

const countFilesRecursive = (dirPath) => {
  if (!fs.existsSync(dirPath)) return 0;
  let count = 0;
  const entries = fs.readdirSync(dirPath, { withFileTypes: true });
  for (const entry of entries) {
    const fullPath = path.resolve(dirPath, entry.name);
    if (entry.isDirectory()) {
      count += countFilesRecursive(fullPath);
    } else {
      count += 1;
    }
  }
  return count;
};

export const exportDbSnapshot = async ({ target = "remote", outDir = "" } = {}) => {
  const timestamp = createTimestamp();
  const snapshotDir = path.resolve(outDir || path.resolve(DB_BACKUP_ROOT_DIR, timestamp));
  ensureDir(snapshotDir);

  const resolved = await connectToTarget(target);
  try {
    const collections = {};

    for (const { key, fileName, model } of COLLECTIONS) {
      const docs = await model.collection.find({}).toArray();
      writeJson(path.resolve(snapshotDir, fileName), docs);
      collections[key] = docs.length;
    }

    const manifest = {
      created_at: new Date().toISOString(),
      source_target: resolved.target,
      source_key: resolved.sourceKey,
      snapshot_dir: snapshotDir,
      collections,
    };
    writeJson(path.resolve(snapshotDir, "manifest.json"), manifest);

    return {
      dir: snapshotDir,
      manifest,
    };
  } finally {
    await disconnectDb();
  }
};

export const importDbSnapshot = async ({
  target = "local",
  fromDir = "",
  replace = true,
} = {}) => {
  const snapshotDir = path.resolve(fromDir || findLatestBackupDir(DB_BACKUP_ROOT_DIR));
  if (!snapshotDir || !fs.existsSync(snapshotDir)) {
    throw new Error("No database backup directory found. Run export-db first or pass --from=<dir>.");
  }

  const resolved = await connectToTarget(target);
  try {
    const collections = {};

    for (const { key, fileName, model } of COLLECTIONS) {
      const filePath = path.resolve(snapshotDir, fileName);
      if (!fs.existsSync(filePath)) {
        collections[key] = {
          imported: 0,
          replaced: replace,
          skipped: true,
        };
        continue;
      }

      const raw = fs.readFileSync(filePath, "utf8");
      const docs = raw.trim() ? JSON.parse(raw) : [];
      const preparedDocs = docs.map((doc) =>
        new model(doc).toObject({ depopulate: true, versionKey: true }),
      );

      if (replace) {
        await model.collection.deleteMany({});
        if (preparedDocs.length > 0) {
          await model.collection.insertMany(preparedDocs, { ordered: false });
        }
      } else if (preparedDocs.length > 0) {
        await model.collection.bulkWrite(
          preparedDocs.map((doc) => ({
            replaceOne: {
              filter: { _id: doc._id },
              replacement: doc,
              upsert: true,
            },
          })),
          { ordered: false },
        );
      }

      collections[key] = {
        imported: preparedDocs.length,
        replaced: replace,
        skipped: false,
      };
    }

    return {
      dir: snapshotDir,
      target: resolved.target,
      target_key: resolved.sourceKey,
      collections,
    };
  } finally {
    await disconnectDb();
  }
};

export const backupUploads = async ({ outDir = "" } = {}) => {
  const timestamp = createTimestamp();
  const backupDir = path.resolve(outDir || path.resolve(UPLOADS_BACKUP_ROOT_DIR, timestamp));
  const copiedDir = path.resolve(backupDir, "persistent");
  ensureDir(backupDir);

  let fileCount = 0;
  let missingSource = false;

  if (fs.existsSync(UPLOADS_PERSISTENT_DIR)) {
    copyDirectoryRecursive(UPLOADS_PERSISTENT_DIR, copiedDir);
    fileCount = countFilesRecursive(copiedDir);
  } else {
    missingSource = true;
    ensureDir(copiedDir);
  }

  const manifest = {
    created_at: new Date().toISOString(),
    source_dir: UPLOADS_PERSISTENT_DIR,
    backup_dir: backupDir,
    copied_dir: copiedDir,
    file_count: fileCount,
    missing_source: missingSource,
  };
  writeJson(path.resolve(backupDir, "manifest.json"), manifest);

  return {
    dir: backupDir,
    copiedDir,
    fileCount,
    missingSource,
  };
};

export const syncRemoteToLocal = async ({ replaceLocal = true } = {}) => {
  const exportResult = await exportDbSnapshot({ target: "remote" });
  const importResult = await importDbSnapshot({
    target: "local",
    fromDir: exportResult.dir,
    replace: replaceLocal,
  });
  const uploadResult = await backupUploads();

  return {
    exported: exportResult,
    imported: importResult,
    uploads: uploadResult,
  };
};

