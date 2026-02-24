import { json, static as serveStatic } from 'express';
import router from './route.js';
import { app, createServers, dbConnect, CLIENT_HOST } from './config.js';
import cors from 'cors';
import multer from 'multer';
import fs from 'fs';
import path from 'path';
import { BACKEND_DIR, PIPELINE_AUTOCROP_DIR, POLYVORE_IMAGES_DIR, UPLOADS_PERSISTENT_DIR, ensureDir } from './utils/paths.js';

const allowedOrigins = (CLIENT_HOST || "")
    .split(",")
    .map((origin) => origin.trim())
    .filter(Boolean);

const LEGACY_UPLOADS_DIR = path.resolve(BACKEND_DIR, 'uploads');

const migrateLegacyUploads = () => {
    if (!fs.existsSync(LEGACY_UPLOADS_DIR)) return 0;
    const files = fs.readdirSync(LEGACY_UPLOADS_DIR, { withFileTypes: true });
    let migrated = 0;
    for (const entry of files) {
        if (!entry.isFile()) continue;
        const src = path.resolve(LEGACY_UPLOADS_DIR, entry.name);
        const dst = path.resolve(UPLOADS_PERSISTENT_DIR, entry.name);
        if (fs.existsSync(dst)) continue;
        fs.copyFileSync(src, dst);
        migrated += 1;
    }
    return migrated;
};

app.use(cors({
    origin: (origin, callback) => {
        if (!origin) {
            return callback(null, true);
        }
        if (allowedOrigins.includes(origin)) {
            return callback(null, true);
        }
        return callback(new Error("Not allowed by CORS"));
    }
}));
app.use(json());
ensureDir(UPLOADS_PERSISTENT_DIR);
ensureDir(PIPELINE_AUTOCROP_DIR);
const migratedLegacyCount = migrateLegacyUploads();
if (migratedLegacyCount > 0) {
    console.log(`Migrated ${migratedLegacyCount} legacy upload file(s) to runtime/uploads/persistent.`);
}
app.use('/uploads', serveStatic(UPLOADS_PERSISTENT_DIR));
if (fs.existsSync(POLYVORE_IMAGES_DIR)) {
    app.use('/catalog-images', serveStatic(POLYVORE_IMAGES_DIR));
} else {
    console.warn(`Catalog images directory not found: ${POLYVORE_IMAGES_DIR}`);
}
app.use('/pipeline-autocrop', serveStatic(PIPELINE_AUTOCROP_DIR));
app.use('/',router);

app.use((err, req, res, next) => {
    if (err instanceof multer.MulterError) {
        if (err.code === "LIMIT_FILE_SIZE") {
            return res.status(413).json({ message: "Uploaded image is too large." });
        }
        return res.status(400).json({ message: err.message || "Upload failed." });
    }

    if (err && typeof err.message === "string" && err.message.toLowerCase().includes("only image uploads are allowed")) {
        return res.status(400).json({ message: err.message });
    }

    if (err && err.message === "Not allowed by CORS") {
        return res.status(403).json({ message: "Not allowed by CORS" });
    }

    return next(err);
});

createServers();
dbConnect();





