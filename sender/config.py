"""Default settings for the QFS1 optical sender."""

from __future__ import annotations

from dataclasses import dataclass


PROTOCOL_VERSION = 1
SYMBOL_SIZE = 1200
BLOCK_SIZE = 64
QR_ECC = "L"
FPS = 20.0
META_INTERVAL = 24
MAX_ZIP_SIZE = 128 * 1024 * 1024
LARGE_ZIP_SIZE = 20 * 1024 * 1024


@dataclass(frozen=True)
class SizePolicy:
    size: int
    tier: str
    warning: str | None = None


def classify_zip_size(size: int) -> SizePolicy:
    if size < 0:
        raise ValueError("ZIP size cannot be negative")
    if size > MAX_ZIP_SIZE:
        raise ValueError(
            f"ZIP is {size:,} bytes; transfers over {MAX_ZIP_SIZE:,} bytes are not supported"
        )
    if size > LARGE_ZIP_SIZE:
        return SizePolicy(size, "LARGE TRANSFER", "Transfer may take a long time.")
    return SizePolicy(size, "NORMAL")
