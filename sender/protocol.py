from __future__ import annotations

import struct
import uuid
import zlib
from dataclasses import dataclass
from typing import Optional, Union

from .config import MAX_ZIP_SIZE, PROTOCOL_VERSION


MAGIC = b"QFS1"
META = 1
DATA = 2
COMMON = struct.Struct(">4sBBBB16sI")
# Keep the QFS1 v1 field offsets for existing senders and receivers.
META_FIXED = struct.Struct(">QHHIIHHH32s")
DATA_FIXED = struct.Struct(">IHHHQH")
CRC32 = struct.Struct(">I")
DATA_PACKET_OVERHEAD = COMMON.size + DATA_FIXED.size + CRC32.size


@dataclass(frozen=True)
class TransferMetadata:
    session_id: bytes
    filename: str
    file_size: int
    symbol_size: int
    source_symbol_count: int
    block_size: int
    sha256: bytes

    @classmethod
    def new(cls, filename: str, file_size: int, symbol_size: int, source_symbol_count: int,
            block_size: int, session_id: Optional[bytes] = None,
            sha256: Optional[bytes] = None) -> "TransferMetadata":
        digest = sha256 or (b"\0" * 32)
        if len(digest) != 32:
            raise ValueError("sha256 must be 32 bytes")
        session = uuid.uuid4().bytes if session_id is None else session_id
        if len(session) != 16:
            raise ValueError("session_id must be 16 bytes")
        return cls(session, filename, file_size, symbol_size, source_symbol_count, block_size, digest)


@dataclass(frozen=True)
class SourceSymbol:
    block_id: int
    symbol_index: int
    source_count: int
    payload: bytes


def split_source_symbols(data: bytes, symbol_size: int, block_size: int) -> list[SourceSymbol]:
    if symbol_size <= 0 or not 1 <= block_size <= 64:
        raise ValueError("Invalid symbol size or block size")
    count = max(1, (len(data) + symbol_size - 1) // symbol_size)
    symbols = []
    for number in range(count):
        block_id, index = divmod(number, block_size)
        block_count = min(block_size, count - block_id * block_size)
        offset = number * symbol_size
        payload = data[offset:offset + symbol_size].ljust(symbol_size, b"\0")
        symbols.append(SourceSymbol(block_id, index, block_count, payload))
    return symbols


def _wrap(packet_type: int, session_id: bytes, body: bytes) -> bytes:
    if len(session_id) != 16:
        raise ValueError("session_id must be 16 bytes")
    common = COMMON.pack(MAGIC, PROTOCOL_VERSION, packet_type, 0, 0, session_id, len(body))
    raw = common + body
    return raw + CRC32.pack(zlib.crc32(raw) & 0xFFFFFFFF)


def encode_meta(meta: TransferMetadata) -> bytes:
    filename = meta.filename.encode("utf-8")
    if len(filename) > 65535:
        raise ValueError("filename is too long")
    body = META_FIXED.pack(meta.file_size, meta.symbol_size, meta.block_size,
                           meta.source_symbol_count, meta.source_symbol_count,
                           100, len(filename), 0, meta.sha256) + filename
    return _wrap(META, meta.session_id, body)


def encode_data(session_id: bytes, symbol: SourceSymbol) -> bytes:
    body = DATA_FIXED.pack(symbol.block_id, symbol.symbol_index, symbol.source_count,
                           symbol.source_count, 1 << symbol.symbol_index, len(symbol.payload)) + symbol.payload
    return _wrap(DATA, session_id, body)


def parse_packet(packet: bytes) -> tuple[int, bytes, Union[TransferMetadata, SourceSymbol]]:
    if len(packet) < COMMON.size + CRC32.size:
        raise ValueError("packet too short")
    magic, version, packet_type, _flags, _reserved, session_id, body_len = COMMON.unpack_from(packet)
    if magic != MAGIC or version != PROTOCOL_VERSION:
        raise ValueError("unsupported packet")
    expected = COMMON.size + body_len + CRC32.size
    if expected != len(packet):
        raise ValueError("packet length mismatch")
    body_end = COMMON.size + body_len
    expected_crc, = CRC32.unpack_from(packet, body_end)
    if zlib.crc32(packet[:body_end]) & 0xFFFFFFFF != expected_crc:
        raise ValueError("CRC32 mismatch")
    body = packet[COMMON.size:body_end]
    if packet_type == META:
        if len(body) < META_FIXED.size:
            raise ValueError("META body too short")
        values = META_FIXED.unpack_from(body)
        file_size, symbol_size, block_size, source_count, _, _, name_len, _, sha256 = values
        if file_size > MAX_ZIP_SIZE:
            raise ValueError(f"META file size exceeds the {MAX_ZIP_SIZE // (1024 * 1024)} MiB ZIP limit")
        filename_bytes = body[META_FIXED.size:]
        if name_len != len(filename_bytes):
            raise ValueError("META filename length mismatch")
        filename = filename_bytes.decode("utf-8")
        return packet_type, session_id, TransferMetadata(session_id, filename, file_size, symbol_size,
                                                         source_count, block_size, sha256)
    if packet_type == DATA:
        if len(body) < DATA_FIXED.size:
            raise ValueError("DATA body too short")
        block_id, symbol_index, source_count, total_count, mask, payload_len = DATA_FIXED.unpack_from(body)
        payload = body[DATA_FIXED.size:]
        if (payload_len != len(payload) or not 0 <= symbol_index < source_count <= 64 or
                total_count < source_count or mask != 1 << symbol_index):
            raise ValueError("DATA payload invalid")
        return packet_type, session_id, SourceSymbol(block_id, symbol_index, source_count, payload)
    raise ValueError("unknown packet type")
