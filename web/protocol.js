const MAGIC = "QFS1";
const VERSION = 1;
export const PACKET_META = 1;
export const PACKET_DATA = 2;

const COMMON_SIZE = 28;
const META_FIXED_SIZE = 58;
const DATA_FIXED_SIZE = 20;
const MAX_ZIP_SIZE = 128 * 1024 * 1024;
const crcTable = new Uint32Array(256);
let crcReady = false;

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
    const nameLength = view.getUint16(COMMON_SIZE + 22);
    const expectedSha256 = [...bytes.slice(COMMON_SIZE + 26, COMMON_SIZE + 58)]
      .map((value) => value.toString(16).padStart(2, "0")).join("");
    const nameBytes = bodyBytes.slice(META_FIXED_SIZE);
    if (fileSize > MAX_ZIP_SIZE) throw new Error(`META file size exceeds the ${MAX_ZIP_SIZE / (1024 * 1024)} MiB ZIP limit`);
    if (symbolSize === 0 || blockSize === 0 || blockSize > 64 ||
        sourceCount !== Math.max(1, Math.ceil(fileSize / symbolSize))) throw new Error("META symbol layout invalid");
    if (nameLength !== nameBytes.length) throw new Error("META filename length mismatch");
    const filename = new TextDecoder().decode(nameBytes);
    return { type, sessionId, sessionKey: sessionHex(sessionId), meta: {
      filename, fileSize, symbolSize, blockSize, sourceCount, expectedSha256,
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
    if (payloadLength !== payload.length || sourceCount > 64 || symbolIndex >= sourceCount ||
        totalCount < sourceCount || mask !== (1n << BigInt(symbolIndex))) throw new Error("DATA payload invalid");
    return { type, sessionId, sessionKey: sessionHex(sessionId), data: {
      blockId, symbolIndex, sourceCount, payload,
    }};
  }
  throw new Error("unknown packet type");
}

export class SourceReceiver {
  constructor(onUpdate = () => {}) {
    this.onUpdate = onUpdate;
    this.reset();
  }

  reset() {
    this.sessionKey = null;
    this.meta = null;
    this.sourceSymbols = new Map();
    this.duplicateCount = 0;
    this.completed = null;
    this.finishing = false;
  }

  feed(input) {
    let packet;
    try {
      packet = parsePacket(input);
    } catch (_) {
      return false;
    }
    if (packet.type === PACKET_META) {
      if (this.sessionKey !== packet.sessionKey) {
        this.reset();
        this.sessionKey = packet.sessionKey;
        this.meta = packet.meta;
      }
      this.onUpdate(this);
      return true;
    }
    if (!this.meta || this.sessionKey !== packet.sessionKey) return false;
    const { blockId, symbolIndex, sourceCount, payload } = packet.data;
    const firstIndex = blockId * this.meta.blockSize;
    const expectedCount = Math.min(this.meta.blockSize, this.meta.sourceCount - firstIndex);
    if (sourceCount !== expectedCount || payload.length !== this.meta.symbolSize) return false;
    const index = firstIndex + symbolIndex;
    if (this.sourceSymbols.has(index)) {
      this.duplicateCount += 1;
    } else {
      this.sourceSymbols.set(index, payload);
      if (this.usefulSymbols === this.meta.sourceCount) this.finish();
    }
    this.onUpdate(this);
    return true;
  }

  async finish() {
    const { sourceSymbols, meta } = this;
    this.finishing = true;
    const archive = new Uint8Array(meta.fileSize);
    for (const [index, payload] of sourceSymbols) {
      const offset = index * meta.symbolSize;
      archive.set(payload.subarray(0, archive.length - offset), offset);
    }
    const digest = await crypto.subtle.digest("SHA-256", archive);
    if (sourceSymbols !== this.sourceSymbols) return;
    const sha256 = [...new Uint8Array(digest)].map((value) => value.toString(16).padStart(2, "0")).join("");
    this.completed = { archive, sha256, verified: sha256 === meta.expectedSha256, filename: meta.filename };
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
  get progress() { return this.meta ? this.usefulSymbols / this.meta.sourceCount : 0; }
}
