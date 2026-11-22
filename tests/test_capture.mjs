import fs from "node:fs";
import vm from "node:vm";
import assert from "node:assert/strict";
import { test } from "node:test";
import { cameraFrameToken, shouldSkipCameraFrame, trackedQrRegion } from "../web/standalone/capture.js";
import { receiverFixture } from "./receiver_fixtures.mjs";

test("frame identity prefers decoded video-frame counters and handles unavailable quality APIs", () => {
  assert.equal(cameraFrameToken({ getVideoPlaybackQuality: () => ({ totalVideoFrames: 7 }), currentTime: 3 }), "frame:7|time:3");
  assert.equal(cameraFrameToken({ getVideoPlaybackQuality: () => { throw new Error(); }, currentTime: 3 }), "time:3");
  assert.equal(cameraFrameToken({}), null);
});

test("stalled frame counters cannot suppress advancing media time or block scanning indefinitely", () => {
  const video = { getVideoPlaybackQuality: () => ({ totalVideoFrames: 7 }), currentTime: 3 };
  const token = cameraFrameToken(video);
  video.currentTime = 3.04;
  assert.notEqual(cameraFrameToken(video), token);
  assert.equal(shouldSkipCameraFrame(token, token, 50), true);
  assert.equal(shouldSkipCameraFrame(token, token, 80), false);
  assert.equal(shouldSkipCameraFrame(null, null, 50), false);
});

test("tracked coordinates map back into source pixels and remain within camera bounds", () => {
  const location = { topLeftCorner: { x: 0, y: 0 }, topRightCorner: { x: 100, y: 0 },
    bottomLeftCorner: { x: 0, y: 100 }, bottomRightCorner: { x: 100, y: 100 } };
  const roi = trackedQrRegion(location, { x: 0, y: 20, width: 200, height: 200,
    imageWidth: 100, imageHeight: 100, sourceWidth: 220, sourceHeight: 240 });
  assert.equal(roi.x, 0); assert.equal(roi.y, 0);
  assert.equal(roi.width, 220); assert.equal(roi.height, 240);
  assert.equal(trackedQrRegion({}, {}), null);
});

test("a dense real QR survives full-frame detection then quiet-zone-preserving ROI cropping", () => {
  const sandbox = { Uint8Array, Uint8ClampedArray, console };
  sandbox.self = sandbox; sandbox.window = sandbox; vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(new URL("../web/vendor/jsqr.js", import.meta.url), "utf8"), sandbox);
  const fixture = receiverFixture("qr");
  const bytes = Buffer.from(fixture.bytes, "base64");
  const qr = Buffer.from(fixture.grayscale, "base64");
  const width = 720, height = 1280, side = fixture.side;
  const originX = Math.floor((width - side) / 2), originY = Math.floor((height - side) / 2);
  const pixels = new Uint8ClampedArray(width * height * 4).fill(255);
  for (let row = 0; row < side; row += 1) for (let col = 0; col < side; col += 1) {
    const offset = ((originY + row) * width + originX + col) * 4;
    pixels[offset] = pixels[offset + 1] = pixels[offset + 2] = qr[row * side + col];
  }
  const result = sandbox.jsQR(pixels, width, height);
  assert.ok(result);
  const roi = trackedQrRegion(result.location, { x: 0, y: 0, width, height,
    imageWidth: width, imageHeight: height, sourceWidth: width, sourceHeight: height });
  assert.ok(roi.width * roi.height < width * height * 0.6);
  const cropped = new Uint8ClampedArray(roi.width * roi.height * 4);
  for (let y = 0; y < roi.height; y += 1) cropped.set(pixels.subarray(((roi.y + y) * width + roi.x) * 4,
    ((roi.y + y) * width + roi.x + roi.width) * 4), y * roi.width * 4);
  const decoded = sandbox.jsQR(cropped, roi.width, roi.height);
  assert.deepEqual([...decoded.binaryData], [...bytes]);
});
