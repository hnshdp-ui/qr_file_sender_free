import fs from "node:fs";
import vm from "node:vm";
import { performance } from "node:perf_hooks";

export async function startEmbeddedWorker({ disableWasm = false } = {}) {
  const html = fs.readFileSync(new URL("../receiver-standalone.html", import.meta.url), "utf8");
  const source = JSON.parse(html.match(/^const QFS_WORKER_SOURCE = (.+);$/m)[1]);
  const messages = [];
  const context = {
    console: { log() {}, error() {}, warn() {} }, Uint8Array, Uint8ClampedArray,
    TextEncoder, TextDecoder, performance, atob, setTimeout, clearTimeout,
    WebAssembly: disableWasm ? undefined : WebAssembly,
    fetch() { throw new Error("Network requests forbidden in standalone worker test"); },
    postMessage(message) { messages.push(message); },
  };
  context.self = context;
  vm.createContext(context); vm.runInContext(source, context);
  for (let attempt = 0; attempt < 500 && !messages.some((m) => m.ready); attempt += 1) {
    await new Promise((resolve) => setTimeout(resolve, 10));
  }
  const ready = messages.find((m) => m.ready);
  if (!ready) throw new Error("Embedded decoder initialization timed out");
  return {
    ready, messages, context,
    async send(data) { await context.onmessage({ data }); return messages.at(-1); },
  };
}
