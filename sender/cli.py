from __future__ import annotations

import argparse
import secrets
import sys
from typing import Optional

from .bundle import cleanup_session, create_zip
from .config import BLOCK_SIZE, FEC_OVERHEAD, FPS, META_INTERVAL, SYMBOL_SIZE, classify_zip_size
from .fec import encode_symbols, schedule_records
from .folder_scan import scan_folder
from .integrity import sha256_file
from .protocol import TransferMetadata, encode_data, encode_meta


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
    parser.add_argument("--symbol-size", type=int, default=DEFAULT_SYMBOL_SIZE)
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
        records, source_count, total_count = encode_symbols(archive.read_bytes(), symbol_size,
                                                             BLOCK_SIZE, FEC_OVERHEAD)
        meta = TransferMetadata.new(archive.name, archive.stat().st_size, symbol_size, source_count,
                                    total_count, BLOCK_SIZE, session_id,
                                    FEC_OVERHEAD, bytes.fromhex(digest))
    except Exception:
        cleanup_session(session_dir)
        raise
    return scan, archive, session_dir, digest, meta, records, size_policy


def _stream(meta: TransferMetadata, records, meta_interval: int,
            start_number: int | None = None, selected_numbers: list[int] | None = None):
    meta_packet = encode_meta(meta)
    data_packets = [encode_data(meta.session_id, record) for record in records]
    sources = {record.block_id * meta.block_size + record.symbol_index + 1: record
               for record in records if record.symbol_index < record.source_count}
    packet_by_record = {id(record): packet for record, packet in zip(records, data_packets)}
    cycle = 0
    while True:
        yield meta_packet
        since_meta = 0
        # The sender already holds the entire archive in memory.
        # Send EVERY block's systematic data before any repair traffic, so a
        # final partial block is never trapped behind 16 blocks of repairs.
        block_count = (meta.source_symbol_count + meta.block_size - 1) // meta.block_size
        ordered = schedule_records(records, cycle=cycle, seed=int.from_bytes(meta.session_id[:8], "big"),
                                   window_blocks=block_count, interleave_sources=True)
        if selected_numbers is not None:
            ordered = [sources[number] for number in selected_numbers if number != 0]
        elif start_number is not None:
            ordered = [sources[number] for number in range(max(1, start_number), meta.source_symbol_count + 1)] + [
                record for record in ordered if record.symbol_index >= record.source_count]
        for record in ordered:
            packet = packet_by_record[id(record)]
            yield packet
            since_meta += 1
            if since_meta >= meta_interval:
                yield meta_packet
                since_meta = 0
        cycle += 1


def main(argv: Optional[list[str]] = None) -> int:
    args = _parser().parse_args(argv)
    folder = args.folder or input("Enter folder path: ").strip().strip('"')
    if not folder:
        print("No folder path supplied.", file=sys.stderr)
        return 2
    if args.fps <= 0 or args.meta_interval <= 0:
        print("FPS and META interval must be positive.", file=sys.stderr)
        return 2
    try:
        from .qr import select_encoder
        encoder = select_encoder(args.qr_encoder)
        scan, archive, session_dir, digest, meta, records, size_policy = build_transfer(folder, args.symbol_size)
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
    data_count, meta_count = qr_cycle_counts(len(records), args.meta_interval)
    cycle_frames = data_count + meta_count
    print(f"QRs per cycle: {cycle_frames:,} (DATA {data_count:,}, META {meta_count:,}; repeats until stopped)")
    print(f"QR payload:    {meta.symbol_size} bytes + protocol header")
    print(f"QR FPS:        {args.fps:g}")
    print(f"QR encoder:    {'ZXing-C++ native' if encoder == 'zxing' else 'Python qrcode (fallback)'}")
    print(f"Size policy:   {size_policy.tier}")
    if size_policy.warning:
        print(f"Warning:       {size_policy.warning}")
    print(f"Session:       {meta.session_id.hex()}")
    if args.no_display:
        try:
            # Advancing the generator encodes META and every DATA packet.
            next(_stream(meta, records, args.meta_interval))
            print("No-display mode: stream prepared successfully.")
        finally:
            cleanup_session(session_dir)
        return 0
    try:
        from .display import show_animated_qr
        stream = _stream(meta, records, args.meta_interval)
        if args.max_frames:
            stream = (packet for index, packet in zip(range(args.max_frames), stream))
        show_animated_qr(stream, "QR File Sender Free", args.fps,
                         lambda: [f"{archive.name}", f"{archive.stat().st_size:,} bytes",
                                  f"QR/cycle: {cycle_frames:,} (source {meta.source_symbol_count:,}, repair {data_count - meta.source_symbol_count:,}, META {meta_count:,})"],
                         cycle_frames=cycle_frames, encoder=encoder,
                         source_count=meta.source_symbol_count, block_size=meta.block_size,
                         stream_factory=lambda start, selected: _stream(meta, records, args.meta_interval, start, selected))
    finally:
        cleanup_session(session_dir)
    return 0
