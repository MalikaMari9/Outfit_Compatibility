import { parseArgs, parseBool, syncRemoteToLocal } from "./lib.js";

const args = parseArgs();

try {
  const result = await syncRemoteToLocal({
    replaceLocal: parseBool(args["replace-local"], true),
  });
  console.log(JSON.stringify(result, null, 2));
} catch (err) {
  console.error(String(err?.message || err));
  process.exit(1);
}

