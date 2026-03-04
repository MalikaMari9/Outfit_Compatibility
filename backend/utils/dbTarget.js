import path from "path";
import { fileURLToPath } from "url";
import { config } from "dotenv";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const BACKEND_DIR = path.resolve(__dirname, "..");

const explicitEnvPath = String(process.env.ENV_FILE || "").trim();
const envPath = explicitEnvPath
  ? (path.isAbsolute(explicitEnvPath)
      ? explicitEnvPath
      : path.resolve(BACKEND_DIR, explicitEnvPath))
  : path.resolve(BACKEND_DIR, ".env");

config({ path: envPath });

export const DEFAULT_LOCAL_DB_URI = "mongodb://127.0.0.1:27017/outfit_compatibility";

export const normalizeDbTarget = (value) => {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "local" || normalized === "remote") {
    return normalized;
  }
  return "";
};

export const resolveDbConfig = (preferredTarget = process.env.DB_TARGET) => {
  const requestedTarget = normalizeDbTarget(preferredTarget);
  const legacyLink = String(process.env.DB_LINK || "").trim();
  const remoteLink = String(process.env.DB_LINK_REMOTE || "").trim();
  const localLink = String(process.env.DB_LINK_LOCAL || "").trim();
  const localUri = localLink || DEFAULT_LOCAL_DB_URI;

  if (requestedTarget === "local") {
    return {
      target: "local",
      uri: localUri,
      sourceKey: localLink ? "DB_LINK_LOCAL" : "DEFAULT_LOCAL_DB_URI",
      envPath,
    };
  }

  if (requestedTarget === "remote") {
    const remoteUri = remoteLink || legacyLink;
    if (!remoteUri) {
      throw new Error("DB_TARGET=remote requires DB_LINK_REMOTE or legacy DB_LINK.");
    }
    return {
      target: "remote",
      uri: remoteUri,
      sourceKey: remoteLink ? "DB_LINK_REMOTE" : "DB_LINK",
      envPath,
    };
  }

  if (legacyLink) {
    return {
      target: "remote",
      uri: legacyLink,
      sourceKey: "DB_LINK",
      envPath,
    };
  }

  if (remoteLink) {
    return {
      target: "remote",
      uri: remoteLink,
      sourceKey: "DB_LINK_REMOTE",
      envPath,
    };
  }

  if (localLink) {
    return {
      target: "local",
      uri: localLink,
      sourceKey: "DB_LINK_LOCAL",
      envPath,
    };
  }

  throw new Error(
    "Missing MongoDB connection settings. Set DB_TARGET with DB_LINK_REMOTE/DB_LINK_LOCAL, or use legacy DB_LINK.",
  );
};
