import { exportDbSnapshot, parseArgs } from "./lib.js";

const args = parseArgs();

try {
  const result = await exportDbSnapshot({
    target: typeof args.target === "string" ? args.target : "remote",
    outDir: typeof args["out-dir"] === "string" ? args["out-dir"] : "",
  });
  console.log(JSON.stringify(result, null, 2));
} catch (err) {
  console.error(String(err?.message || err));
  process.exit(1);
}

