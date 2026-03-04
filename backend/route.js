import { Router } from "express";
import { ACTIVE_DB_SOURCE_KEY, ACTIVE_DB_TARGET } from "./config.js";
import { register, login } from "./controllers/auth.js";
import { getUserData, updateUserData } from "./controllers/dashboard.js";
import {
    deleteAdminUser,
    getAdminReportById,
    getAdminReports,
    getAdminUserById,
    getAdminUsers,
    updateAdminReport,
    updateAdminUser,
} from "./controllers/admin.js";
import { addWardrobeItem, backfillWardrobeFeatures, deleteWardrobeItem, getWardrobe } from "./controllers/wardrobe.js";
import { compatibilityCheck, explainFromFacts, recommendOutfit } from "./controllers/inference.js";
import { submitFeedback } from "./controllers/feedback.js";
import { wardrobeUpload, tempUpload } from "./utils/img.js";

const router = Router();
const OLLAMA_HOST = String(process.env.OLLAMA_HOST || "http://127.0.0.1:11434").replace(/\/+$/, "");

const fetchWithTimeout = async (url, timeoutMs = 3000) => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
        return await fetch(url, { signal: controller.signal });
    } finally {
        clearTimeout(timer);
    }
};

//auth routes
router.post("/signup", register);
router.post("/signin", login);

//
router.get("/account", getUserData);
router.put("/account", updateUserData);
router.get("/admin/users", getAdminUsers);
router.get("/admin/users/:id", getAdminUserById);
router.patch("/admin/users/:id", updateAdminUser);
router.delete("/admin/users/:id", deleteAdminUser);
router.get("/admin/reports", getAdminReports);
router.get("/admin/reports/:id", getAdminReportById);
router.patch("/admin/reports/:id", updateAdminReport);

router.get("/wardrobe", getWardrobe);
router.post("/wardrobe", wardrobeUpload.single("image"), addWardrobeItem);
router.post("/wardrobe/backfill-features", backfillWardrobeFeatures);
router.delete("/wardrobe/:id", deleteWardrobeItem);
router.post("/recommend", tempUpload.single("image"), recommendOutfit);
router.post(
    "/compatibility",
    tempUpload.fields([
        { name: "top", maxCount: 1 },
        { name: "bottom", maxCount: 1 },
        { name: "full_body", maxCount: 1 },
    ]),
    compatibilityCheck,
);
router.post("/explain", explainFromFacts);
router.post("/feedback", submitFeedback);

router.get("/health", (req, res) => {
    return res.status(200).json({ status: "ok" });
});

router.get("/health/db", (req, res) => {
    return res.status(200).json({
        status: "ok",
        db_target: ACTIVE_DB_TARGET || "unknown",
        db_source: ACTIVE_DB_SOURCE_KEY || "unknown",
    });
});

router.get("/health/ollama", async (req, res) => {
    try {
        const response = await fetchWithTimeout(`${OLLAMA_HOST}/api/tags`, 3000);
        if (!response.ok) {
            return res.status(502).json({
                status: "down",
                host: OLLAMA_HOST,
                http_status: response.status,
            });
        }

        const payload = await response.json();
        const models = Array.isArray(payload?.models)
            ? payload.models
                .map((m) => String(m?.name || "").trim())
                .filter(Boolean)
            : [];

        return res.status(200).json({
            status: "ok",
            host: OLLAMA_HOST,
            model_count: models.length,
            models: models.slice(0, 20),
        });
    } catch (err) {
        return res.status(502).json({
            status: "down",
            host: OLLAMA_HOST,
            error: String(err?.message || err),
        });
    }
});

export default router;



