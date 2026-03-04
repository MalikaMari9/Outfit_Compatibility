import { backupUploads, parseArgs } from "./lib.js";

const args = parseArgs();

try {
  const result = await backupUploads({
    outDir: typeof args["out-dir"] === "string" ? args["out-dir"] : "",
  });
  console.log(JSON.stringify(result, null, 2));
} catch (err) {
  console.error(String(err?.message || err));
  process.exit(1);
}

