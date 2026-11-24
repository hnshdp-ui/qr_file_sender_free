import fs from "node:fs";
import vm from "node:vm";
import assert from "node:assert/strict";
import { webcrypto } from "node:crypto";
import { test } from "node:test";
import { startEmbeddedWorker } from "./standalone_worker_harness.mjs";
import { receiverFixture, runTestPython } from "./receiver_fixtures.mjs";

runTestPython(["scripts/build_standalone_receiver.py"]);
const html = fs.readFileSync(new URL("../dist/pages/index.html", import.meta.url), "utf8");
const script = html.match(/<script>\s*([\s\S]*?)<\/script>/)[1];

function page({ camera = true, protocol = "https:" } = {}) {
  const elements = new Map(), workers = [], blobs = new Map(), rafs = new Map(), intervals = new Map(), timeouts = new Map();
  let stopped = 0, now = 0, timerId = 0;
  const element = (id) => {
    if (!elements.has(id)) elements.set(id, {
      hidden: ["result", "download", "share"].includes(id), listeners: {},
      addEventListener(event, callback) { this.listeners[event] = callback; },
      removeAttribute(name) { delete this[name]; },
      async play() {},
      readyState: 4, videoWidth: 320, videoHeight: 180, currentTime: 0,
      requestVideoFrameCallback() { throw new Error("Video-frame callbacks must not be required"); },
      getContext() { return { drawImage() {}, getImageData(_x, _y, width, height) { return { width, height, data: new Uint8ClampedArray(width * height * 4) }; } }; },
    });
    return elements.get(id);
  };
  const context = {
    console, crypto: webcrypto, TextEncoder, TextDecoder, Uint8Array, Uint8ClampedArray,
    Uint32Array, DataView, BigInt, Blob, File, performance: { now: () => now },
    requestAnimationFrame(callback) { const id = ++timerId; rafs.set(id, callback); return id; },
    cancelAnimationFrame(id) { rafs.delete(id); },
    setInterval(callback) { const id = ++timerId; intervals.set(id, callback); return id; },
    clearInterval(id) { intervals.delete(id); },
    setTimeout(callback) { const id = ++timerId; timeouts.set(id, callback); return id; },
    clearTimeout(id) { timeouts.delete(id); },
    location: { protocol }, isSecureContext: protocol === "https:",
    document: { getElementById: element },
    navigator: camera ? { mediaDevices: { async getUserMedia() { return { getTracks: () => [{ stop() { stopped += 1; } }] }; } } } : {},
    URL: { createObjectURL(blob) { const url = `blob:test-${blobs.size}`; blobs.set(url, blob); return url; }, revokeObjectURL() {} },
    Worker: class { constructor(url) { this.url = url; workers.push(this); } terminate() { this.terminated = true; } postMessage(data) { this.lastMessage = data; } },
    addEventListener() {},
    fetch() { throw new Error("Network access is forbidden"); },
  };
  context.self = context; context.window = context;
  vm.createContext(context); vm.runInContext(script, context);
  return {
    context, element, workers, blobs, stopped: () => stopped,
    advance(ms) { now += ms; },
    nextFrame(fresh = true, elapsed = 100) { now += elapsed; if (fresh) element("camera").currentTime += elapsed / 1000; const [id, callback] = rafs.entries().next().value; rafs.delete(id); callback(now); },
    tickMetrics() { for (const callback of intervals.values()) callback(); },
    expireWorker() { for (const [id, callback] of [...timeouts]) { timeouts.delete(id); callback(); } },
  };
}

function makePackets(expectedDigestCorrect = true) {
  const fixture = receiverFixture(expectedDigestCorrect ? "valid" : "invalid");
  return {
    packets: fixture.packets.map((packet) => Uint8Array.from(Buffer.from(packet, "base64"))),
    bytes: Uint8Array.from(Buffer.from(fixture.bytes, "base64")),
  };
}

test("repair numbers cover missing META and sources, and selected replay completes the same task", async () => {
  const ui = page(), { packets } = makePackets();
  assert.equal(ui.element("missing-numbers").value, "0");
  assert.match(ui.element("missing-sources").textContent, /无法确定总分片数/);
  await ui.element("start").listeners.click();
  const parse = vm.runInContext("QFSProtocol.parsePacket", ui.context);
  const meta = packets.find((packet) => parse(packet).meta);
  const sources = packets.filter((packet) => parse(packet).data);
  const feed = (binary) => ui.workers[0].onmessage({ data: { binary } });
  feed(sources[0]);
  assert.equal(ui.element("missing-numbers").value, "0");
  feed(meta);
  assert.equal(ui.element("missing-numbers").value, "1-3");
  feed(sources[0]); feed(sources[2]);
  assert.equal(ui.element("missing-numbers").value, "2");
  feed(meta);
  assert.equal(ui.element("missing-numbers").value, "2");
  feed(sources[1]);
  for (let i = 0; i < 30 && ui.element("result").hidden; i += 1) await new Promise((resolve) => setTimeout(resolve, 5));
  assert.equal(ui.element("result").hidden, false);
  assert.equal(ui.element("missing-numbers").value, "");
  assert.equal(ui.element("copy-missing").disabled, true);
});

test("standalone HTML includes executable classic scripts without external resources or ad dependencies", () => {
  assert.equal((html.match(/<script>/g) || []).length, 1);
  assert.doesNotMatch(html, /<script[^>]+src=|<link[^>]+href=/i);
  assert.doesNotMatch(script, /^import\s|^export\s|createRewardedAdProvider|googletag|serviceWorker/m);
  assert.match(html, /connect-src 'none'/);
  new vm.Script(script);
});

test("insecure pages point users to the GitHub Pages receiver", async () => {
  const ui = page({ camera: false, protocol: "http:" });
  assert.equal(ui.element("environment").hidden, false);
  assert.match(ui.element("environment").textContent, /GitHub Pages/);
  await ui.element("start").listeners.click();
  assert.match(ui.element("status").textContent, /GitHub Pages.*HTTPS/);
  assert.equal(ui.element("result").hidden, true);
});

test("live scan counters update even when the worker finds no QR", async () => {
  const ui = page();
  await ui.element("start").listeners.click();
  const worker = ui.workers[0];
  worker.onmessage({ data: { ready: true } });
  ui.nextFrame();
  assert.equal(worker.lastMessage.width, 320);
  worker.onmessage({ data: { binary: null } });
  ui.tickMetrics();
  assert.match(ui.element("metrics").textContent, /扫描 1 帧 · 解码 1 次 · QR 0 个 · QFS 0 帧/);
  assert.match(ui.element("metrics").textContent, /320×180/);
});

test("fallback ignores repeated camera frames and can scan fresh frames 33 ms apart", async () => {
  const ui = page(); await ui.element("start").listeners.click();
  const worker = ui.workers[0]; worker.onmessage({ data: { ready: true } });
  ui.nextFrame(); worker.onmessage({ data: { binary: null } });
  ui.nextFrame(false, 30); ui.tickMetrics();
  assert.match(ui.element("metrics").textContent, /扫描 1 帧/);
  assert.match(ui.element("metrics").textContent, /跳过重复视频帧 1/);
  ui.nextFrame(true, 33); worker.onmessage({ data: { binary: null } }); ui.tickMetrics();
  assert.match(ui.element("metrics").textContent, /扫描 2 帧/);
});

test("video callbacks scan consecutive 30 FPS frames and stop with the camera", async () => {
  const ui = page(), video = ui.element("camera");
  let callback, frameId = 0;
  video.requestVideoFrameCallback = (next) => { callback = next; return ++frameId; };
  video.cancelVideoFrameCallback = (id) => { assert.equal(id, frameId); callback = undefined; };
  await ui.element("start").listeners.click();
  const worker = ui.workers[0]; worker.onmessage({ data: { ready: true } });
  for (let index = 1; index <= 30; index += 1) {
    ui.advance(1000 / 30);
    callback(index * 1000 / 30, { presentedFrames: index });
    worker.onmessage({ data: { binary: null } });
  }
  ui.tickMetrics();
  assert.match(ui.element("metrics").textContent, /扫描 30 帧/);
  assert.match(ui.element("metrics").textContent, /rVFC/);
  ui.element("stop").listeners.click();
  assert.equal(callback, undefined);
});

test("a stalled video callback switches to the animation-frame fallback", async () => {
  const ui = page(), video = ui.element("camera");
  video.requestVideoFrameCallback = () => 1;
  await ui.element("start").listeners.click();
  ui.workers[0].onmessage({ data: { ready: true } });
  ui.advance(250); ui.expireWorker();
  ui.nextFrame(); ui.tickMetrics();
  assert.match(ui.element("metrics").textContent, /扫描 1 帧/);
  assert.match(ui.element("metrics").textContent, /rAF/);
});

test("a frozen counter and clock still capture at least 10 times per second", async () => {
  const ui = page(); await ui.element("start").listeners.click();
  const worker = ui.workers[0]; worker.onmessage({ data: { ready: true } });
  ui.element("camera").getVideoPlaybackQuality = () => ({ totalVideoFrames: 7 });
  for (let i = 0; i < 60; i += 1) {
    ui.nextFrame(false, 1000 / 60);
    worker.onmessage({ data: { binary: null, decodeMs: 10 } });
  }
  ui.tickMetrics();
  const attempts = Number(ui.element("metrics").textContent.match(/解码 (\d+) 次/)[1]);
  assert.ok(attempts >= 10 && attempts <= 13, `attempts=${attempts}`);
  assert.match(ui.element("metrics").textContent, /保底重采/);
});

test("fallback uses an advancing clock when the video frame counter freezes", async () => {
  const ui = page(); await ui.element("start").listeners.click();
  const worker = ui.workers[0]; worker.onmessage({ data: { ready: true } });
  ui.element("camera").getVideoPlaybackQuality = () => ({ totalVideoFrames: 7 });
  for (let i = 0; i < 60; i += 1) {
    ui.nextFrame(true, 1000 / 60);
    worker.onmessage({ data: { binary: null } });
  }
  ui.tickMetrics();
  const attempts = Number(ui.element("metrics").textContent.match(/解码 (\d+) 次/)[1]);
  assert.ok(attempts >= 27 && attempts <= 30, `attempts=${attempts}`);
});

test("diagnostic export records scan gates, worker delay and packet numbers without file contents", async () => {
  const ui = page(), { packets } = makePackets();
  await ui.element("start").listeners.click();
  const worker = ui.workers[0]; worker.onmessage({ data: { ready: true, decoder: "ZXING-WASM" } });
  ui.nextFrame();
  ui.nextFrame();
  ui.advance(100);
  worker.onmessage({ data: { binary: packets[0], decodeMs: 10 } });
  ui.nextFrame();
  worker.onmessage({ data: { binary: packets[1], decodeMs: 10 } });
  ui.advance(1000); ui.tickMetrics();
  ui.element("export-log").listeners.click();
  const blob = ui.blobs.get(ui.element("export-log").href);
  const report = JSON.parse(await blob.text());
  assert.equal(report.version, "v20261122.1");
  assert.ok(report.events.some((event) => event.event === "sample" && event.busySkips > 0 &&
    event.captureSource === "rAF" && event.symbolSize > 0));
  assert.ok(report.events.some((event) => event.event === "packet" && event.sourceNumber === 0));
  assert.ok(report.events.some((event) => event.event === "packet" && event.sourceNumber === 1));
  assert.doesNotMatch(await blob.text(), /测试\.zip|"payload"|"binary"/);
});

test("valid QFS locks a padded ROI and three misses restore full-frame search", async () => {
  const ui = page(), { packets } = makePackets();
  await ui.element("start").listeners.click();
  const worker = ui.workers[0]; worker.onmessage({ data: { ready: true } });
  ui.nextFrame();
  worker.onmessage({ data: { binary: packets[0], location: {
    topLeftCorner: { x: 100, y: 40 }, topRightCorner: { x: 220, y: 40 },
    bottomLeftCorner: { x: 100, y: 140 }, bottomRightCorner: { x: 220, y: 140 },
  } } });
  ui.nextFrame();
  assert.equal(worker.lastMessage.width, 168);
  assert.equal(worker.lastMessage.height, 140);
  for (let i = 0; i < 3; i += 1) {
    worker.onmessage({ data: { binary: null } });
    if (i < 2) ui.nextFrame();
  }
  ui.tickMetrics(); assert.match(ui.element("metrics").textContent, /区域 全画面/);
  ui.nextFrame(); assert.equal(worker.lastMessage.width, 320);
});

test("worker startup timeout falls back to main-thread scanning", async () => {
  const ui = page();
  ui.context.jsQR = () => null;
  await ui.element("start").listeners.click();
  ui.expireWorker();
  assert.equal(ui.workers[0].terminated, true);
  ui.nextFrame(); ui.tickMetrics();
  assert.match(ui.element("metrics").textContent, /扫描 1 帧/);
  assert.match(ui.element("metrics").textContent, /Worker 启动超时/);
});

test("stalled worker cannot permanently block later camera frames", async () => {
  const ui = page();
  ui.context.jsQR = () => null;
  await ui.element("start").listeners.click();
  ui.workers[0].onmessage({ data: { ready: true } });
  ui.nextFrame();
  ui.advance(2600); ui.nextFrame(); ui.tickMetrics();
  assert.equal(ui.workers[0].terminated, true);
  assert.match(ui.element("metrics").textContent, /扫描 2 帧/);
  assert.match(ui.element("metrics").textContent, /Worker 响应超时/);
});

test("camera frame errors are visible and do not terminate the scan loop", async () => {
  const ui = page();
  ui.context.jsQR = () => null;
  await ui.element("start").listeners.click();
  ui.expireWorker();
  ui.element("frame").getContext = () => { throw new Error("canvas denied"); };
  ui.nextFrame(); ui.tickMetrics();
  assert.match(ui.element("metrics").textContent, /canvas denied/);
  ui.nextFrame();
  assert.match(ui.element("status").textContent, /画面读取或解码失败/);
});

test("embedded WASM initializes without network and returns a no-QR result", async () => {
  const worker = await startEmbeddedWorker(html);
  assert.equal(worker.ready.decoder, "ZXING-WASM");
  const result = await worker.send({ pixels: new Uint8ClampedArray(16 * 16 * 4), width: 16, height: 16 });
  assert.equal(result.binary, null);
  assert.equal(result.decoder, "ZXING-WASM");
});

test("blocked WebAssembly initializes the jsQR worker fallback", async () => {
  const worker = await startEmbeddedWorker(html, { disableWasm: true });
  assert.equal(worker.ready.decoder, "JSQR");
  assert.ok(worker.ready.fallbackReason);
  const result = await worker.send({ pixels: new Uint8ClampedArray(16 * 16 * 4), width: 16, height: 16 });
  assert.equal(result.binary, null);
  assert.equal(result.decoder, "JSQR");
});

test("a WASM decode failure falls back to jsQR without resetting the transfer", async () => {
  const worker = await startEmbeddedWorker(html);
  worker.context.ZXingWASM.readBarcodes = async () => { throw new Error("simulated WASM failure"); };
  const result = await worker.send({ pixels: new Uint8ClampedArray(16 * 16 * 4), width: 16, height: 16 });
  assert.equal(result.binary, null);
  assert.match(result.decoder, /JSQR/);
  assert.match(result.fallbackReason, /simulated WASM failure/);
});

test("task timing starts on META, survives pause, and freezes after verification", async () => {
  const ui = page(), { packets } = makePackets();
  await ui.element("start").listeners.click();
  ui.advance(9000); ui.tickMetrics();
  assert.match(ui.element("task-time").textContent, /00:00/);
  ui.workers[0].onmessage({ data: { binary: packets[0] } });
  ui.advance(61000); ui.tickMetrics();
  assert.match(ui.element("task-time").textContent, /01:01/);
  await ui.element("stop").listeners.click();
  ui.advance(10000); ui.tickMetrics();
  assert.match(ui.element("task-time").textContent, /01:11/);
  await ui.element("start").listeners.click();
  for (const binary of packets.slice(1)) ui.workers[1].onmessage({ data: { binary } });
  for (let i = 0; i < 30 && ui.element("result").hidden; i += 1) await new Promise((resolve) => setTimeout(resolve, 5));
  assert.equal(ui.element("result").hidden, false);
  const completedTime = ui.element("task-time").textContent;
  assert.match(completedTime, /01:11.*完成时间/);
  ui.advance(60000); ui.tickMetrics();
  assert.equal(ui.element("task-time").textContent, completedTime);
  ui.element("reset").listeners.click();
  assert.match(ui.element("task-time").textContent, /00:00/);
  assert.doesNotMatch(ui.element("task-time").textContent, /完成时间/);
});

for (const valid of [true, false]) test(`real protocol packets ${valid ? "unlock direct save" : "fail SHA-256 without enabling save"}`, async () => {
  const ui = page(), { packets, bytes } = makePackets(valid);
  await ui.element("start").listeners.click();
  assert.equal(ui.workers.length, 1);
  for (const binary of packets) ui.workers[0].onmessage({ data: { binary } });
  for (let i = 0; i < 30 && !ui.stopped(); i += 1) await new Promise((resolve) => setTimeout(resolve, 5));
  assert.ok(ui.stopped());
  assert.equal(ui.element("result").hidden, !valid);
  if (valid) {
    const file = ui.blobs.get(ui.element("download").href);
    assert.equal(file.name, "测试.zip");
    assert.deepEqual(new Uint8Array(await file.arrayBuffer()), bytes);
    assert.match(ui.element("status").textContent, /直接保存/);
  } else assert.match(ui.element("status").textContent, /校验失败/);
});
