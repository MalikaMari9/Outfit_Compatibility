import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

export const BACKEND_DIR = path.resolve(__dirname, "..");
export const PROJECT_ROOT = path.resolve(BACKEND_DIR, "..");

export const RUNTIME_DIR = path.resolve(PROJECT_ROOT, "runtime");
export const UPLOADS_ROOT_DIR = path.resolve(RUNTIME_DIR, "uploads");
export const UPLOADS_PERSISTENT_DIR = path.resolve(UPLOADS_ROOT_DIR, "persistent");
export const UPLOADS_TEMP_DIR = path.resolve(UPLOADS_ROOT_DIR, "temp");

export const PIPELINE_DIR = path.resolve(PROJECT_ROOT, "services", "pipeline");
export const PIPELINE_SCRIPTS_DIR = path.resolve(PIPELINE_DIR, "scripts");
export const PIPELINE_CONFIG_PATH = path.resolve(
  PIPELINE_DIR,
  "configs",
  "pipeline_config.json",
);

export const BACKEND_CACHE_DIR = path.resolve(RUNTIME_DIR, "cache", "backend_api");
export const PIPELINE_CACHE_DIR = path.resolve(RUNTIME_DIR, "cache", "pipeline");
export const PIPELINE_AUTOCROP_DIR = path.resolve(PIPELINE_CACHE_DIR, "autocrop");
export const POLYVORE_IMAGES_DIR = path.resolve(
  PROJECT_ROOT,
  "assets",
  "data",
  "polyvore_outfits",
  "images",
);

export const ensureDir = (dirPath) => {
  if (!fs.existsSync(dirPath)) {
    fs.mkdirSync(dirPath, { recursive: true });
  }
  return dirPath;
};
