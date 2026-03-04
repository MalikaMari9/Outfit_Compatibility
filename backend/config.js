import e from "express";
import http from 'http';
import https from 'https';
import fs from 'fs';
import { connect } from 'mongoose';
import { resolveDbConfig } from "./utils/dbTarget.js";
let resolvedDb = {
    target: "",
    uri: "",
    sourceKey: "",
};
let dbConfigError = "";

try {
    resolvedDb = resolveDbConfig();
} catch (err) {
    dbConfigError = String(err?.message || err);
}

const DB_LINK = resolvedDb.uri;
const HTTP_PORT = process.env.HTTP_PORT;
const HTTPS_PORT = process.env.HTTPS_PORT;
export const JWT_SECRET = process.env.JWT_SECRET;
export const JWT_EXPIRES_IN = process.env.JWT_EXPIRES_IN;
export const CLIENT_HOST = process.env.CLIENT_HOST;
export const ACTIVE_DB_TARGET = resolvedDb.target;
export const ACTIVE_DB_SOURCE_KEY = resolvedDb.sourceKey;

const requiredEnv = [
    { key: "DB connection", value: DB_LINK },
    { key: "HTTP_PORT", value: HTTP_PORT },
    { key: "JWT_SECRET", value: JWT_SECRET },
];

const missing = requiredEnv.filter((item) => !item.value).map((item) => item.key);
if (missing.length > 0) {
    console.error(`Missing required environment variables: ${missing.join(", ")}`);
    if (dbConfigError) {
        console.error(dbConfigError);
    }
    process.exit(1);
}

export const app = e();

export const createServers = async () => {
    http.createServer(app).listen(HTTP_PORT, ()=>{
        console.log(`HTTP server running at port: ${HTTP_PORT}`)
    });   
}

// Connect MongoDB
export const dbConnect = async () => {
  connect(DB_LINK)
    .then(() => {
        const suffix = ACTIVE_DB_TARGET ? ` (${ACTIVE_DB_TARGET})` : "";
        console.log(`MongoDB connected${suffix}`);
    })
    .catch(err => console.error(err));  
}
