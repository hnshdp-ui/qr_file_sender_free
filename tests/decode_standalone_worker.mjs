import fs from "node:fs";
import { startEmbeddedWorker } from "./standalone_worker_harness.mjs";

const input = JSON.parse(fs.readFileSync(0, "utf8"));
const worker = await startEmbeddedWorker({ disableWasm: input.disableWasm });
const result = await worker.send({ pixels: Uint8ClampedArray.from(Buffer.from(input.rgba, "base64")),
  width: input.width, height: input.height, tracking: false });
if (!result.binary) throw new Error(result.error || "No QR decoded");
process.stdout.write(JSON.stringify({ decoder: result.decoder,
  binary: Buffer.from(result.binary).toString("base64"), location: result.location,
  readyDecoder: worker.ready.decoder }));
