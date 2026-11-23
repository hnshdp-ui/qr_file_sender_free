from __future__ import annotations

import argparse
import secrets
import sys
from itertools import islice
from typing import Optional

from .bundle import cleanup_session, create_zip
from .config import BLOCK_SIZE, FPS, META_INTERVAL, QR_ECC, SYMBOL_SIZE, classify_zip_size
from .folder_scan import scan_folder
from .integrity import sha256_file
from .protocol import DATA_PACKET_OVERHEAD, TransferMetadata, encode_data, encode_meta, split_source_symbols


DEFAULT_SYMBOL_SIZE = SYMBOL_SIZE
DEFAULT_META_INTERVAL = META_INTERVAL


def qr_cycle_counts(data_count: int, meta_interval: int) -> tuple[int, int]:
    """Return DATA and META frame counts for one complete replay cycle."""
    return data_count, 1 + data_count // meta_interval


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Send a folder over an animated QR optical channel")
    parser.add_argument("folder", nargs="?", help="folder to archive")
    parser.add_argument("--fps", type=float, default=FPS)
    parser.add_argument("--qr-encoder", choices=("auto", "zxing", "qrcode"), default="auto",
                        help="auto prefers native ZXing-C++; qrcode forces the Python fallback")
    parser.add_argument("--symbol-size", type=int, default=DEFAULT_SYMBOL_SIZE,
                        help="DATA payload bytes, capped at the QR capacity (default: %(default)s)")
    parser.add_argument("--qr-ecc", type=str.upper, choices=("L", "M", "Q", "H"), default=QR_ECC,
                        help="QR error correction level (default: %(default)s)")
    parser.add_argument("--meta-interval", type=int, default=DEFAULT_META_INTERVAL)
    parser.add_argument("--no-display", action="store_true", help="build and validate the stream without Tkinter")
    parser.add_argument("--max-frames", type=int, default=0, help="stop stream generation after N frames")
    return parser


def build_transfer(folder: str, symbol_size: int = DEFAULT_SYMBOL_SIZE):
    session_id = secrets.token_bytes(16)
    scan = scan_folder(folder)
    archive, session_dir = create_zip(scan, session_id.hex())
    try:
        size_policy = classify_zip_size(archive.stat().st_size)
        digest = sha256_file(archive)
        symbols = split_source_symbols(archive.read_bytes(), symbol_size, BLOCK_SIZE)
        meta = TransferMetadata.new(archive.name, archive.stat().st_size, symbol_size, len(symbols),
                                    BLOCK_SIZE, session_id, bytes.fromhex(digest))
    except Exception:
        cleanup_session(session_dir)
        raise
    return scan, archive, session_dir, digest, meta, symbols, size_policy


def _stream(meta: TransferMetadata, symbols, meta_interval: int,
            start_number: int | None = None, selected_numbers: list[int] | None = None):
    meta_packet = encode_meta(meta)
    numbers = (range(max(1, start_number or 0), len(symbols) + 1)
               if selected_numbers is None else (number for number in selected_numbers if number))
    packets = [encode_data(meta.session_id, symbols[number - 1]) for number in numbers]
    while True:
        yield meta_packet
        for index, packet in enumerate(packets, 1):
            yield packet
            if index % meta_interval == 0:
                yield meta_packet


def main(argv: Optional[list[str]] = None) -> int:
    args = _parser().parse_args(argv)
    folder = args.folder or input("Enter folder path: ").strip().strip('"')
    if not folder:
        print("No folder path supplied.", file=sys.stderr)
        return 2
    if args.fps <= 0 or args.meta_interval <= 0:
        print("FPS and META interval must be positive.", file=sys.stderr)
        return 2
    if args.symbol_size <= 0:
        print("--symbol-size must be positive.", file=sys.stderr)
        return 2
    try:
        from .qr import max_binary_packet_size, select_encoder
        encoder = select_encoder(args.qr_encoder)
        max_symbol_size = max_binary_packet_size(args.qr_ecc, encoder) - DATA_PACKET_OVERHEAD
        symbol_size = min(args.symbol_size, max_symbol_size)
        if symbol_size < args.symbol_size:
            print(f"Warning: --symbol-size {args.symbol_size} exceeds QR capacity for {encoder} "
                  f"with ECC {args.qr_ecc}. Using {symbol_size} bytes per symbol.", file=sys.stderr)
        scan, archive, session_dir, digest, meta, symbols, size_policy = build_transfer(folder, symbol_size)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print("\nScanning...")
    print(f"Files:        {scan.files}")
    print(f"Folders:      {scan.folders}")
    print(f"Total size:   {scan.total_size:,} bytes")
    if scan.excluded:
        print("\nExcluded:")
        for item in scan.excluded:
            print(f"- {item}")
    print("\nZIP ready")
    print(f"Size:         {archive.stat().st_size:,} bytes")
    print(f"SHA-256:      {digest}")
    print(f"Source symbols: {meta.source_symbol_count}")
    data_count, meta_count = qr_cycle_counts(len(symbols), args.meta_interval)
    cycle_frames = data_count + meta_count
    print(f"QRs per cycle: {cycle_frames:,} (source {data_count:,}, META {meta_count:,})")
    print(f"QR payload:    {meta.symbol_size} bytes + protocol header · ECC {args.qr_ecc}")
    print(f"QR FPS:        {args.fps:g}")
    print(f"QR encoder:    {'ZXing-C++ native' if encoder == 'zxing' else 'Python qrcode (fallback)'}")
    print(f"Size policy:   {size_policy.tier}")
    if size_policy.warning:
        print(f"Warning:       {size_policy.warning}")
    print(f"Session:       {meta.session_id.hex()}")
    if args.no_display:
        try:
            next(_stream(meta, symbols, args.meta_interval))
            print("No-display mode: stream prepared successfully.")
        finally:
            cleanup_session(session_dir)
        return 0
    try:
        from .display import show_animated_qr

        def playback_stream(start=None, selected=None):
            stream = _stream(meta, symbols, args.meta_interval, start, selected)
            if args.max_frames and start is None and selected is None:
                return islice(stream, max(0, args.max_frames))
            return stream

        show_animated_qr(playback_stream(), "QR File Sender Free", args.fps,
                         lambda: [f"{archive.name}", f"{archive.stat().st_size:,} bytes"],
                         cycle_frames=cycle_frames, encoder=encoder, ecc=args.qr_ecc,
                         source_count=meta.source_symbol_count, block_size=meta.block_size,
                         stream_factory=playback_stream)
    finally:
        cleanup_session(session_dir)
    return 0
