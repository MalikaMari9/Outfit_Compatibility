import { importDbSnapshot, parseArgs, parseBool } from "./lib.js";

const args = parseArgs();

try {
  const result = await importDbSnapshot({
    target: typeof args.target === "string" ? args.target : "local",
    fromDir: typeof args.from === "string" ? args.from : "",
    replace: parseBool(args.replace, true),
  });
  console.log(JSON.stringify(result, null, 2));
} catch (err) {
  console.error(String(err?.message || err));
  process.exit(1);
}

