from __future__ import annotations

import struct
import uuid
import zlib
from dataclasses import dataclass
from typing import Optional, Union

from .config import FEC_OVERHEAD, MAX_ZIP_SIZE, PROTOCOL_VERSION
from .fec import FECRecord


MAGIC = b"QFS1"
META = 1
DATA = 2
COMMON = struct.Struct(">4sBBBB16sI")
META_FIXED = struct.Struct(">QHHIIHHH32s")
DATA_FIXED = struct.Struct(">IHHHQH")


@dataclass(frozen=True)
class TransferMetadata:
    session_id: bytes
    filename: str
    file_size: int
    symbol_size: int
    source_symbol_count: int
    total_symbol_count: int
    block_size: int
    overhead_x100: int
    sha256: bytes

    @classmethod
    def new(cls, filename: str, file_size: int, symbol_size: int, source_symbol_count: int,
            total_symbol_count: int, block_size: int, session_id: Optional[bytes] = None,
            overhead: float = FEC_OVERHEAD, sha256: Optional[bytes] = None) -> "TransferMetadata":
        digest = sha256 or (b"\0" * 32)
        if len(digest) != 32:
            raise ValueError("sha256 must be 32 bytes")
        session = uuid.uuid4().bytes if session_id is None else session_id
        if len(session) != 16:
            raise ValueError("session_id must be 16 bytes")
        return cls(session, filename, file_size, symbol_size,
                   source_symbol_count, total_symbol_count, block_size, round(overhead * 100), digest)


def _wrap(packet_type: int, session_id: bytes, body: bytes) -> bytes:
    if len(session_id) != 16:
        raise ValueError("session_id must be 16 bytes")
    common = COMMON.pack(MAGIC, PROTOCOL_VERSION, packet_type, 0, 0, session_id, len(body))
    raw = common + body
    return raw + struct.pack(">I", zlib.crc32(raw) & 0xFFFFFFFF)


def encode_meta(meta: TransferMetadata) -> bytes:
    filename = meta.filename.encode("utf-8")
    if len(filename) > 65535:
        raise ValueError("filename is too long")
    body = META_FIXED.pack(meta.file_size, meta.symbol_size, meta.block_size,
                           meta.source_symbol_count, meta.total_symbol_count,
                           meta.overhead_x100, len(filename), 0, meta.sha256) + filename
    return _wrap(META, meta.session_id, body)


def encode_data(session_id: bytes, record: FECRecord) -> bytes:
    body = DATA_FIXED.pack(record.block_id, record.symbol_index, record.source_count,
                           record.total_count, record.mask, len(record.payload)) + record.payload
    return _wrap(DATA, session_id, body)


def parse_packet(packet: bytes) -> tuple[int, bytes, Union[TransferMetadata, FECRecord]]:
    if len(packet) < COMMON.size + 4:
        raise ValueError("packet too short")
    magic, version, packet_type, _flags, _reserved, session_id, body_len = COMMON.unpack_from(packet)
    if magic != MAGIC or version != PROTOCOL_VERSION:
        raise ValueError("unsupported packet")
    expected = COMMON.size + body_len + 4
    if expected != len(packet):
        raise ValueError("packet length mismatch")
    body_end = COMMON.size + body_len
    expected_crc = struct.unpack(">I", packet[body_end:])[0]
    if zlib.crc32(packet[:body_end]) & 0xFFFFFFFF != expected_crc:
        raise ValueError("CRC32 mismatch")
    body = packet[COMMON.size:body_end]
    if packet_type == META:
        if len(body) < META_FIXED.size:
            raise ValueError("META body too short")
        values = META_FIXED.unpack_from(body)
        file_size, symbol_size, block_size, source_count, total_count, overhead_x100, name_len, _, sha256 = values
        if file_size > MAX_ZIP_SIZE:
            raise ValueError("META file size exceeds the 30 MB ZIP policy")
        filename_bytes = body[META_FIXED.size:]
        if name_len != len(filename_bytes):
            raise ValueError("META filename length mismatch")
        filename = filename_bytes.decode("utf-8")
        return packet_type, session_id, TransferMetadata(session_id, filename, file_size, symbol_size,
                                                          source_count, total_count, block_size, overhead_x100, sha256)
    if packet_type == DATA:
        if len(body) < DATA_FIXED.size:
            raise ValueError("DATA body too short")
        block_id, symbol_index, source_count, total_count, mask, payload_len = DATA_FIXED.unpack_from(body)
        payload = body[DATA_FIXED.size:]
        if (payload_len != len(payload) or not mask or source_count == 0 or
                source_count > 64 or total_count < source_count or symbol_index >= total_count):
            raise ValueError("DATA payload invalid")
        return packet_type, session_id, FECRecord(block_id, symbol_index, source_count,
                                                   total_count, mask, payload)
    raise ValueError("unknown packet type")
