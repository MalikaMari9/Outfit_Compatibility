import multer from "multer";
import fsPromises from "fs/promises";
import { UPLOADS_PERSISTENT_DIR, UPLOADS_TEMP_DIR, ensureDir } from "./paths.js";

const DEFAULT_MAX_UPLOAD_MB = 10;
const parsedMaxMb = Number(process.env.MAX_UPLOAD_MB || DEFAULT_MAX_UPLOAD_MB);
const maxUploadMb = Number.isFinite(parsedMaxMb) && parsedMaxMb > 0 ? parsedMaxMb : DEFAULT_MAX_UPLOAD_MB;
const maxUploadBytes = Math.floor(maxUploadMb * 1024 * 1024);

const allowedImageMimeTypes = new Set([
  "image/jpeg",
  "image/jpg",
  "image/png",
  "image/webp",
  "image/bmp",
]);

const fileFilter = (req, file, cb) => {
  if (!file || !allowedImageMimeTypes.has(String(file.mimetype || "").toLowerCase())) {
    return cb(new Error("Only image uploads are allowed (jpeg, png, webp, bmp)."));
  }
  return cb(null, true);
};

const buildStorage = (uploadDir) =>
  multer.diskStorage({
    destination: (req, file, cb) => {
      cb(null, uploadDir);
    },
    filename: (req, file, cb) => {
      const safeName = file.originalname.replace(/[^a-zA-Z0-9._-]/g, "_");
      const uniqueName = `${Date.now()}_${safeName}`;
      cb(null, uniqueName);
    },
  });

const createUpload = ({ destinationDir, maxFiles }) =>
  multer({
    storage: buildStorage(destinationDir),
    fileFilter,
    limits: {
      fileSize: maxUploadBytes,
      files: maxFiles,
    },
  });

ensureDir(UPLOADS_PERSISTENT_DIR);
ensureDir(UPLOADS_TEMP_DIR);

export const wardrobeUpload = createUpload({
  destinationDir: UPLOADS_PERSISTENT_DIR,
  maxFiles: 1,
});

export const tempUpload = createUpload({
  destinationDir: UPLOADS_TEMP_DIR,
  maxFiles: 4,
});

export const extractUploadedFilePaths = (req) => {
  const out = [];
  if (req?.file?.path) {
    out.push(String(req.file.path));
  }

  const files = req?.files;
  if (Array.isArray(files)) {
    for (const file of files) {
      if (file?.path) out.push(String(file.path));
    }
  } else if (files && typeof files === "object") {
    for (const key of Object.keys(files)) {
      const slot = files[key];
      if (!Array.isArray(slot)) continue;
      for (const file of slot) {
        if (file?.path) out.push(String(file.path));
      }
    }
  }
  return Array.from(new Set(out));
};

export const removeFiles = async (filePaths) => {
  if (!Array.isArray(filePaths) || filePaths.length === 0) return;
  await Promise.all(
    filePaths.map(async (p) => {
      const target = String(p || "").trim();
      if (!target) return;
      try {
        await fsPromises.unlink(target);
      } catch {
        // best-effort cleanup
      }
    }),
  );
};

// Backward-compatible default for existing imports.
export default wardrobeUpload;
