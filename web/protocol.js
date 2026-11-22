const MAGIC = "QFS1";
const VERSION = 1;
export const PACKET_META = 1;
export const PACKET_DATA = 2;

const COMMON_SIZE = 28;
const META_FIXED_SIZE = 58;
const DATA_FIXED_SIZE = 20;
const MAX_ZIP_SIZE = 30 * 1024 * 1024;
const crcTable = new Uint32Array(256);
let crcReady = false;

function clockMs() { return typeof globalThis.performance?.now === "function" ? globalThis.performance.now() : Date.now(); }

function percentile(values, fraction) {
  if (!values.length) return 0;
  const sorted = [...values].sort((left, right) => left - right);
  return sorted[Math.min(sorted.length - 1, Math.floor((sorted.length - 1) * fraction))];
}

function initCrc() {
  if (crcReady) return;
  for (let i = 0; i < 256; i += 1) {
    let c = i;
    for (let bit = 0; bit < 8; bit += 1) c = (c & 1) ? (0xedb88320 ^ (c >>> 1)) : (c >>> 1);
    crcTable[i] = c >>> 0;
  }
  crcReady = true;
}

export function crc32(input) {
  initCrc();
  let crc = 0xffffffff;
  for (const value of input) crc = crcTable[(crc ^ value) & 0xff] ^ (crc >>> 8);
  return (crc ^ 0xffffffff) >>> 0;
}

function ascii(view, offset, length) {
  let result = "";
  for (let i = 0; i < length; i += 1) result += String.fromCharCode(view.getUint8(offset + i));
  return result;
}

function sessionHex(sessionId) {
  return [...sessionId].map((value) => value.toString(16).padStart(2, "0")).join("");
}

export function parsePacket(input) {
  const bytes = input instanceof Uint8Array ? input : new Uint8Array(input);
  if (bytes.length < COMMON_SIZE + 4) throw new Error("packet too short");
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  if (ascii(view, 0, 4) !== MAGIC || view.getUint8(4) !== VERSION) throw new Error("unsupported packet");
  const type = view.getUint8(5);
  const sessionId = bytes.slice(8, 24);
  const bodyLength = view.getUint32(24);
  const bodyEnd = COMMON_SIZE + bodyLength;
  if (bodyEnd + 4 !== bytes.length) throw new Error("packet length mismatch");
  const expectedCrc = view.getUint32(bodyEnd);
  if (crc32(bytes.slice(0, bodyEnd)) !== expectedCrc) throw new Error("CRC32 mismatch");
  const bodyBytes = bytes.slice(COMMON_SIZE, bodyEnd);
  if (type === PACKET_META) {
    if (bodyLength < META_FIXED_SIZE) throw new Error("META body too short");
    const fileSize = Number(view.getBigUint64(COMMON_SIZE));
    const symbolSize = view.getUint16(COMMON_SIZE + 8);
    const blockSize = view.getUint16(COMMON_SIZE + 10);
    const sourceCount = view.getUint32(COMMON_SIZE + 12);
    const totalCount = view.getUint32(COMMON_SIZE + 16);
    const overheadX100 = view.getUint16(COMMON_SIZE + 20);
    const nameLength = view.getUint16(COMMON_SIZE + 22);
    const expectedSha256 = [...bytes.slice(COMMON_SIZE + 26, COMMON_SIZE + 58)]
      .map((value) => value.toString(16).padStart(2, "0")).join("");
    const nameBytes = bodyBytes.slice(META_FIXED_SIZE);
    if (fileSize > MAX_ZIP_SIZE) throw new Error("META file size exceeds the 30 MB ZIP policy");
    if (nameLength !== nameBytes.length) throw new Error("META filename length mismatch");
    const filename = new TextDecoder().decode(nameBytes);
    return { type, sessionId, sessionKey: sessionHex(sessionId), meta: {
      filename, fileSize, symbolSize, blockSize, sourceCount, totalCount, overheadX100, expectedSha256,
    }};
  }
  if (type === PACKET_DATA) {
    if (bodyLength < DATA_FIXED_SIZE) throw new Error("DATA body too short");
    const blockId = view.getUint32(COMMON_SIZE);
    const symbolIndex = view.getUint16(COMMON_SIZE + 4);
    const sourceCount = view.getUint16(COMMON_SIZE + 6);
    const totalCount = view.getUint16(COMMON_SIZE + 8);
    const mask = view.getBigUint64(COMMON_SIZE + 10);
    const payloadLength = view.getUint16(COMMON_SIZE + 18);
    const payload = bodyBytes.slice(DATA_FIXED_SIZE);
    if (payloadLength !== payload.length || mask === 0n || sourceCount === 0 || sourceCount > 64 ||
        totalCount < sourceCount || symbolIndex >= totalCount) throw new Error("DATA payload invalid");
    return { type, sessionId, sessionKey: sessionHex(sessionId), data: {
      blockId, symbolIndex, sourceCount, totalCount, mask, payload,
    }};
  }
  throw new Error("unknown packet type");
}

function xorBytes(left, right) {
  const result = left.slice();
  for (let i = 0; i < result.length; i += 1) result[i] ^= right[i];
  return result;
}

function singletonIndex(mask, k) {
  if (mask === 0n || (mask & (mask - 1n)) !== 0n) return -1;
  for (let i = 0; i < k; i += 1) if ((mask & (1n << BigInt(i))) !== 0n) return i;
  return -1;
}

class IncrementalBlockDecoder {
  constructor(size) {
    this.size = size;
    this.rows = new Map();
    this.known = new Map();
    this.bits = Array.from({ length: size }, (_, i) => 1n << BigInt(i));
  }

  add(record) {
    let mask = record.mask, payload = record.payload.slice();
    // Existing rows are in reduced row-echelon form. Reduce each new equation
    // once instead of solving the entire history after every received frame.
    for (const [pivot, row] of this.rows) {
      if (mask & this.bits[pivot]) {
        mask ^= row.mask;
        payload = xorBytes(payload, row.payload);
      }
    }
    if (!mask) return [];
    const pivot = this.bits.findIndex((bit) => Boolean(mask & bit));
    for (const row of this.rows.values()) {
      if (row.mask & this.bits[pivot]) {
        row.mask ^= mask;
        row.payload = xorBytes(row.payload, payload);
      }
    }
    this.rows.set(pivot, { mask, payload });
    const recovered = [];
    for (const row of this.rows.values()) {
      const index = singletonIndex(row.mask, this.size);
      if (index >= 0 && !this.known.has(index)) {
        this.known.set(index, row.payload);
        recovered.push([index, row.payload]);
      }
    }
    return recovered;
  }
}

export class FountainReceiver {
  constructor(onUpdate = () => {}) {
    this.onUpdate = onUpdate;
    this.reset();
  }

  reset() {
    this.sessionKey = null;
    this.meta = null;
    this.blocks = new Map();
    this.sourceSymbols = new Map();
    this.solvedBlockIds = new Set();
    this.blockDecoders = new Map();
    this.uniqueDataCount = 0;
    this.packetCount = 0;
    this.duplicateCount = 0;
    this.invalidCount = 0;
    this.uniqueRepairEquations = 0;
    this.lastUsefulAt = 0;
    this.completed = null;
    this.finishing = false;
    this.parseLatencies = [];
    this.solveLatencies = [];
    this.shaLatencies = [];
  }

  feed(input) {
    let packet;
    const parseStarted = clockMs();
    try {
      packet = parsePacket(input);
      this.parseLatencies.push(clockMs() - parseStarted);
    } catch (error) {
      this.parseLatencies.push(clockMs() - parseStarted);
      this.invalidCount += 1;
      this.onUpdate(this);
      return false;
    }
    if (packet.type === PACKET_META) {
      if (this.sessionKey !== packet.sessionKey) {
        this.reset();
        this.sessionKey = packet.sessionKey;
      }
      this.meta = packet.meta;
      this.onUpdate(this);
      return true;
    }
    if (!this.meta || this.sessionKey !== packet.sessionKey) return false;
    const expectedBlockCount = Math.min(this.meta.blockSize, this.meta.sourceCount - packet.data.blockId * this.meta.blockSize);
    if (packet.data.payload.length !== this.meta.symbolSize || packet.data.blockId * this.meta.blockSize >= this.meta.sourceCount ||
        packet.data.sourceCount !== expectedBlockCount ||
        packet.data.mask >= (1n << BigInt(expectedBlockCount))) return false;
    this.packetCount += 1;
    const block = this.blocks.get(packet.data.blockId) || new Map();
    if (block.has(packet.data.symbolIndex)) { this.duplicateCount += 1; this.onUpdate(this); return true; }
    block.set(packet.data.symbolIndex, packet.data);
    this.blocks.set(packet.data.blockId, block);
    this.uniqueDataCount += 1;
    if (packet.data.symbolIndex >= packet.data.sourceCount) this.uniqueRepairEquations += 1;
    const beforeUseful = this.sourceSymbols.size;
    this.trySolveBlock(packet.data.blockId, packet.data);
    if (this.sourceSymbols.size > beforeUseful) this.lastUsefulAt = Date.now();
    this.onUpdate(this);
    return true;
  }

  trySolveBlock(blockId, record) {
    if (this.completed || this.finishing || this.solvedBlockIds.has(blockId)) return;
    if (!record) return;
    const decoder = this.blockDecoders.get(blockId) || new IncrementalBlockDecoder(record.sourceCount);
    this.blockDecoders.set(blockId, decoder);
    const solveStarted = clockMs();
    const recovered = decoder.add(record);
    this.solveLatencies.push(clockMs() - solveStarted);
    for (const [index, payload] of recovered) this.sourceSymbols.set(blockId * this.meta.blockSize + index, payload);
    if (decoder.known.size === record.sourceCount) this.solvedBlockIds.add(blockId);
    if (this.sourceSymbols.size >= this.meta.sourceCount) this.finish();
  }

  async finish() {
    if (this.completed || this.finishing || !this.meta) return;
    this.finishing = true;
    const shaStarted = clockMs();
    const bytes = new Uint8Array(this.meta.sourceCount * this.meta.symbolSize);
    for (let i = 0; i < this.meta.sourceCount; i += 1) bytes.set(this.sourceSymbols.get(i), i * this.meta.symbolSize);
    const archive = bytes.slice(0, this.meta.fileSize);
    const digest = await crypto.subtle.digest("SHA-256", archive);
    const sha256 = [...new Uint8Array(digest)].map((value) => value.toString(16).padStart(2, "0")).join("");
    this.shaLatencies.push(clockMs() - shaStarted);
    const verified = sha256 === this.meta.expectedSha256;
    this.completed = { archive, sha256, verified, filename: this.meta.filename };
    this.onUpdate(this);
  }

  get usefulSymbols() { return this.sourceSymbols.size; }
  missingSources(limit = 32) {
    if (!this.meta) return [];
    const missing = [];
    for (let index = 0; index < this.meta.sourceCount && missing.length < limit; index += 1) {
      if (!this.sourceSymbols.has(index)) missing.push(index);
    }
    return missing;
  }
  get progress() { return this.meta ? Math.min(1, this.usefulSymbols / this.meta.sourceCount) : 0; }
  get blocksTotal() { return this.meta ? Math.ceil(this.meta.sourceCount / this.meta.blockSize) : 0; }
  get blocksSolved() {
    if (!this.meta) return 0;
    let solved = 0;
    for (let blockId = 0; blockId < this.blocksTotal; blockId += 1) {
      const expected = Math.min(this.meta.blockSize, this.meta.sourceCount - blockId * this.meta.blockSize);
      let count = 0;
      for (let index = 0; index < expected; index += 1) if (this.sourceSymbols.has(blockId * this.meta.blockSize + index)) count += 1;
      if (count === expected) solved += 1;
    }
    return solved;
  }
  get blocksPartial() {
    if (!this.meta) return 0;
    let partial = 0;
    for (const blockId of this.blocks.keys()) {
      const expected = Math.min(this.meta.blockSize, this.meta.sourceCount - blockId * this.meta.blockSize);
      let count = 0;
      for (let index = 0; index < expected; index += 1) if (this.sourceSymbols.has(blockId * this.meta.blockSize + index)) count += 1;
      if (count > 0 && count < expected) partial += 1;
    }
    return partial;
  }
  get worstBlockDeficit() {
    if (!this.meta) return 0;
    let worst = 0;
    for (let blockId = 0; blockId < this.blocksTotal; blockId += 1) {
      const expected = Math.min(this.meta.blockSize, this.meta.sourceCount - blockId * this.meta.blockSize);
      let count = 0;
      for (let index = 0; index < expected; index += 1) if (this.sourceSymbols.has(blockId * this.meta.blockSize + index)) count += 1;
      worst = Math.max(worst, expected - count);
    }
    return worst;
  }
  get timeSinceLastUsefulSeconds() {
    return this.lastUsefulAt ? Math.max(0, (Date.now() - this.lastUsefulAt) / 1000) : null;
  }
  get solverProfile() {
    return {
      parseP50Ms: percentile(this.parseLatencies, 0.5), parseP95Ms: percentile(this.parseLatencies, 0.95),
      solveP50Ms: percentile(this.solveLatencies, 0.5), solveP95Ms: percentile(this.solveLatencies, 0.95),
      shaP50Ms: percentile(this.shaLatencies, 0.5), shaP95Ms: percentile(this.shaLatencies, 0.95),
    };
  }
}
