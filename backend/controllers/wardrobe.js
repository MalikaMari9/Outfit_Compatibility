import clothing from "../models/clothing.js";
import path from "path";
import fs from "fs";
import { verifyToken } from "../utils/jwt.js";
import { isValidObjectId } from "mongoose";
import { UPLOADS_PERSISTENT_DIR } from "../utils/paths.js";
import { runWardrobeFeatureExtraction } from "../utils/pipeline.js";

const requireAuth = async (req, res) => {
  const authHeader = req.headers.authorization;
  if (!authHeader) {
    res.status(401).json({ message: "Unauthorized access" });
    return null;
  }

  const decoded = await verifyToken(authHeader);
  if (!decoded) {
    res.status(401).json({ message: "Unauthorized access" });
    return null;
  }

  return decoded;
};

const toBool = (value, fallback = false) => {
  if (value === undefined || value === null) return fallback;
  const norm = String(value).trim().toLowerCase();
  if (!norm) return fallback;
  if (["1", "true", "yes", "on"].includes(norm)) return true;
  if (["0", "false", "no", "off"].includes(norm)) return false;
  return fallback;
};

const toSafeLimit = (value, fallback = 80, min = 1, max = 300) => {
  const n = Number(value);
  if (!Number.isFinite(n)) return fallback;
  return Math.max(min, Math.min(max, Math.round(n)));
};

export const getWardrobe = async (req, res) => {
  try {
    const decoded = await requireAuth(req, res);
    if (!decoded) return;

    const items = await clothing
      .find({ userId: decoded.id })
      .sort({ createdAt: -1 });

    return res.status(200).json({
      items,
    });
  } catch (err) {
    console.error(err);
    return res.status(500).json({ message: "Server error" });
  }
};

export const addWardrobeItem = async (req, res) => {
  try {
    const decoded = await requireAuth(req, res);
    if (!decoded) return;

    if (!req.file) {
      return res.status(400).json({ message: "No file uploaded" });
    }

    const { name, category, description } = req.body || {};
    const normalizedCategory = category ? String(category).toLowerCase() : "";
    if (!["top", "bottom"].includes(normalizedCategory)) {
      return res.status(400).json({ message: "Category must be top or bottom" });
    }

    const details = {
      name: name || "Untitled Item",
      category: normalizedCategory,
    };

    if (description) details.description = description;

    try {
      const featurePayload = await runWardrobeFeatureExtraction({
        imagePath: String(req.file.path),
        semantic: normalizedCategory,
      });
      details.features = featurePayload;
      details.features_status = "ok";
    } catch (featureErr) {
      details.features_status = "error";
      details.features_error = String(featureErr?.message || featureErr);
    }

    const newItem = await clothing.create({
      imagePath: `/uploads/${req.file.filename}`,
      userId: decoded.id,
      details,
    });

    return res.status(201).json({ item: newItem });
  } catch (err) {
    console.error(err);
    return res.status(500).json({ message: "Server error" });
  }
};

export const deleteWardrobeItem = async (req, res) => {
  try {
    const decoded = await requireAuth(req, res);
    if (!decoded) return;

    const { id } = req.params;
    if (!isValidObjectId(id)) {
      return res.status(400).json({ message: "Invalid item id" });
    }

    const item = await clothing.findOne({ _id: id, userId: decoded.id });
    if (!item) {
      return res.status(404).json({ message: "Item not found" });
    }

    await clothing.deleteOne({ _id: id, userId: decoded.id });
    return res.status(200).json({ message: "Item deleted" });
  } catch (err) {
    console.error(err);
    return res.status(500).json({ message: "Server error" });
  }
};

export const backfillWardrobeFeatures = async (req, res) => {
  try {
    const decoded = await requireAuth(req, res);
    if (!decoded) return;

    const force = toBool(req.body?.force ?? req.query?.force, false);
    const limit = toSafeLimit(req.body?.limit ?? req.query?.limit, 80);

    const startedAt = Date.now();
    const items = await clothing
      .find({ userId: decoded.id })
      .sort({ createdAt: -1 })
      .limit(limit);

    const summary = {
      total_scanned: items.length,
      updated: 0,
      skipped_existing: 0,
      missing_file: 0,
      failed: 0,
      force,
      limit,
      failures: [],
    };

    for (const item of items) {
      const existingOk =
        item?.details?.features &&
        typeof item.details.features === "object" &&
        !Array.isArray(item.details.features) &&
        String(item?.details?.features_status || "").trim().toLowerCase() === "ok";

      if (existingOk && !force) {
        summary.skipped_existing += 1;
        continue;
      }

      const imagePath = String(item.imagePath || "").trim();
      const fileName = path.basename(imagePath);
      const localPath = path.resolve(UPLOADS_PERSISTENT_DIR, fileName);
      const category = String(item?.details?.category || "").trim().toLowerCase();

      if (!fileName || !fs.existsSync(localPath)) {
        summary.missing_file += 1;
        summary.failed += 1;
        const details = {
          ...(item.details || {}),
          features_status: "error",
          features_error: `Image file not found in runtime uploads: ${fileName || "(empty)"}`,
        };
        item.details = details;
        await item.save();
        if (summary.failures.length < 30) {
          summary.failures.push({
            item_id: String(item._id),
            imagePath,
            error: "missing_file",
          });
        }
        continue;
      }

      try {
        const featurePayload = await runWardrobeFeatureExtraction({
          imagePath: localPath,
          semantic: category,
        });

        item.details = {
          ...(item.details || {}),
          features: featurePayload,
          features_status: "ok",
          features_error: "",
        };
        await item.save();
        summary.updated += 1;
      } catch (err) {
        summary.failed += 1;
        item.details = {
          ...(item.details || {}),
          features_status: "error",
          features_error: String(err?.message || err),
        };
        await item.save();
        if (summary.failures.length < 30) {
          summary.failures.push({
            item_id: String(item._id),
            imagePath,
            error: String(err?.message || err),
          });
        }
      }
    }

    return res.status(200).json({
      message: "Wardrobe feature backfill completed.",
      summary: {
        ...summary,
        duration_ms: Date.now() - startedAt,
      },
    });
  } catch (err) {
    console.error(err);
    return res.status(500).json({ message: "Server error" });
  }
};
