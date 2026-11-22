import fs from "node:fs";
import vm from "node:vm";

const input = JSON.parse(fs.readFileSync(0, "utf8"));
const context = { console, Uint8ClampedArray, Uint8Array };
context.window = context;
context.self = context;
vm.runInNewContext(fs.readFileSync(new URL("../web/vendor/jsqr.js", import.meta.url), "utf8"), context);
const result = context.jsQR(Uint8ClampedArray.from(Buffer.from(input.rgba, "base64")), input.width, input.height, { inversionAttempts: "attemptBoth" });
if (!result) process.exit(2);
process.stdout.write(Buffer.from(result.binaryData).toString("base64"));
