import assert from "node:assert/strict";
import { webcrypto } from "node:crypto";
import { test } from "node:test";
import { SourceReceiver, crc32, parsePacket } from "../web/protocol.js";

if (!globalThis.crypto) globalThis.crypto = webcrypto;

function packet(type, session, body) {
  const raw = new Uint8Array(28 + body.length);
  raw.set(new TextEncoder().encode("QFS1"), 0);
  raw[4] = 1; raw[5] = type; raw.set(session, 8);
  new DataView(raw.buffer).setUint32(24, body.length);
  raw.set(body, 28);
  const result = new Uint8Array(raw.length + 4);
  result.set(raw);
  new DataView(result.buffer).setUint32(raw.length, crc32(raw));
  return result;
}

test("web protocol module exports binary packet helpers", () => {
  assert.equal(typeof crc32, "function");
  assert.equal(typeof parsePacket, "function");
});

test("receiver accepts a 128 MiB ZIP and rejects a ZIP one byte larger", () => {
  const limit = 128 * 1024 * 1024;
  const session = new Uint8Array(16);
  const meta = new Uint8Array(58), view = new DataView(meta.buffer);
  view.setUint16(8, 1200);
  view.setUint16(10, 64);

  function metaPacket(size) {
    view.setBigUint64(0, BigInt(size));
    view.setUint32(12, Math.ceil(size / 1200));
    return packet(1, session, meta);
  }

  assert.equal(parsePacket(metaPacket(limit)).meta.fileSize, limit);
  assert.throws(() => parsePacket(metaPacket(limit + 1)), /128 MiB ZIP limit/);
});

test("browser receiver reconstructs and verifies a small binary transfer", async () => {
  const session = Uint8Array.from({ length: 16 }, (_, index) => index + 1);
  const file = new TextEncoder().encode("hello qf");
  const digest = new Uint8Array(await webcrypto.subtle.digest("SHA-256", file));
  const filename = new TextEncoder().encode("sample.zip");
  const meta = new Uint8Array(58 + filename.length);
  const metaView = new DataView(meta.buffer);
  metaView.setBigUint64(0, BigInt(file.length));
  metaView.setUint16(8, 4); metaView.setUint16(10, 64);
  metaView.setUint32(12, 2); metaView.setUint32(16, 4);
  metaView.setUint16(20, 400); metaView.setUint16(22, filename.length);
  meta.set(digest, 26); meta.set(filename, 58);
  const receiver = new SourceReceiver();
  receiver.feed(packet(1, session, meta));
  for (const [index, payload] of [[1, file.slice(4, 8)], [0, file.slice(0, 4)]]) {
    const body = new Uint8Array(20 + payload.length);
    const view = new DataView(body.buffer);
    view.setUint32(0, 0); view.setUint16(4, index); view.setUint16(6, 2);
    view.setUint16(8, 4); view.setBigUint64(10, 1n << BigInt(index));
    view.setUint16(18, payload.length); body.set(payload, 20);
    receiver.feed(packet(2, session, body));
  }
  for (let attempt = 0; attempt < 20 && !receiver.completed; attempt += 1) await new Promise((resolve) => setTimeout(resolve, 0));
  assert.ok(receiver.completed);
  assert.equal(receiver.completed.verified, true);
  assert.deepEqual([...receiver.completed.archive], [...file]);
});

test("receiver tracks missing source numbers and duplicates across blocks", async () => {
  const session = new Uint8Array(16).fill(7);
  const file = new TextEncoder().encode("abcdefghijklmnop");
  const digest = new Uint8Array(await webcrypto.subtle.digest("SHA-256", file));
  const filename = new TextEncoder().encode("blocks.zip");
  const meta = new Uint8Array(58 + filename.length), view = new DataView(meta.buffer);
  view.setBigUint64(0, BigInt(file.length));
  view.setUint16(8, 4); view.setUint16(10, 2);
  view.setUint32(12, 4); view.setUint32(16, 16);
  view.setUint16(20, 400); view.setUint16(22, filename.length);
  meta.set(digest, 26); meta.set(filename, 58);
  const receiver = new SourceReceiver();
  receiver.feed(packet(1, session, meta));
  function data(blockId, index, mask, offset) {
    const body = new Uint8Array(24), bodyView = new DataView(body.buffer);
    bodyView.setUint32(0, blockId); bodyView.setUint16(4, index);
    bodyView.setUint16(6, 2); bodyView.setUint16(8, 8);
    bodyView.setBigUint64(10, mask); bodyView.setUint16(18, 4);
    body.set(file.slice(offset, offset + 4), 20);
    return packet(2, session, body);
  }
  receiver.feed(data(0, 0, 1n, 0));
  assert.equal(receiver.usefulSymbols, 1);
  assert.deepEqual(receiver.missingSources(), [1, 2, 3]);
  assert.equal(receiver.feed(data(0, 2, 1n, 0)), false);
  assert.equal(receiver.feed(data(0, 1, 3n, 4)), false);
  receiver.feed(data(0, 0, 1n, 0));
  assert.equal(receiver.duplicateCount, 1);
  receiver.feed(data(1, 0, 1n, 8)); receiver.feed(data(1, 1, 2n, 12));
  assert.deepEqual(receiver.missingSources(), [1]);
  assert.equal(receiver.finishing, false);
  receiver.feed(data(0, 1, 2n, 4));
  for (let i = 0; i < 20 && !receiver.completed; i += 1) await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(receiver.completed.verified, true);
  assert.deepEqual([...receiver.completed.archive], [...file]);
});
