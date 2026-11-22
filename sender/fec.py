from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Dict, Iterable, List, Sequence

from .config import BLOCK_SIZE as DEFAULT_BLOCK_SIZE, FEC_OVERHEAD as DEFAULT_OVERHEAD


def _xor_into(target: bytearray, source: bytes) -> None:
    for index, value in enumerate(source):
        target[index] ^= value


def _mask_for_mixed(k: int, block_id: int, parity_index: int) -> int:
    """Deterministically create a sparse XOR equation mask.

    The first K parity symbols are exact duplicates (one per source symbol).
    The remaining symbols use several low degrees, which makes peeling work
    well under optical loss while retaining a Gaussian-elimination fallback.
    """
    if parity_index < k:
        return 1 << parity_index
    rng = random.Random((block_id + 1) * 0x9E3779B1 ^ (parity_index + 1) * 0x85EBCA77)
    choices = [(4, 5), (8, 20), (12, 30), (16, 30), (24, 15)]
    pick = rng.randrange(sum(weight for _, weight in choices))
    degree = choices[-1][0]
    for candidate, weight in choices:
        if pick < weight:
            degree = min(candidate, k)
            break
        pick -= weight
    # Every source is the designated base of at least one mixed equation.
    # This prevents an unlucky optical loss pattern from erasing a source
    # from the entire equation graph before the rank-recovery fallback runs.
    base = (parity_index - k) % k
    selected = [base]
    remaining = [index for index in range(k) if index != base]
    selected.extend(rng.sample(remaining, max(0, degree - 1)))
    mask = 0
    for index in selected:
        mask |= 1 << index
    return mask


def _equation_payload(source: Sequence[bytes], mask: int, symbol_size: int) -> bytes:
    result = bytearray(symbol_size)
    for index in range(len(source)):
        if mask & (1 << index):
            _xor_into(result, source[index])
    return bytes(result)


@dataclass(frozen=True)
class FECRecord:
    block_id: int
    symbol_index: int
    source_count: int
    total_count: int
    mask: int
    payload: bytes


def encode_symbols(data: bytes, symbol_size: int, block_size: int = DEFAULT_BLOCK_SIZE,
                   overhead: float = DEFAULT_OVERHEAD) -> tuple[List[FECRecord], int, int]:
    if symbol_size <= 0 or block_size <= 0:
        raise ValueError("symbol_size and block_size must be positive")
    source_symbols = [data[offset:offset + symbol_size].ljust(symbol_size, b"\0")
                      for offset in range(0, len(data), symbol_size)]
    if not source_symbols:
        source_symbols = [b"\0" * symbol_size]
    records: List[FECRecord] = []
    for block_id, start in enumerate(range(0, len(source_symbols), block_size)):
        block = source_symbols[start:start + block_size]
        k = len(block)
        total = max(k + 1, int(k * overhead))
        for symbol_index, payload in enumerate(block):
            records.append(FECRecord(block_id, symbol_index, k, total, 1 << symbol_index, payload))
        for symbol_index in range(k, total):
            mask = _mask_for_mixed(k, block_id, symbol_index - k)
            records.append(FECRecord(block_id, symbol_index, k, total, mask,
                                     _equation_payload(block, mask, symbol_size)))
    return records, len(source_symbols), len(records)


def schedule_records(records: Iterable[FECRecord], cycle: int = 0, seed: int = 0,
                     window_blocks: int = 16, interleave_sources: bool = False) -> List[FECRecord]:
    """Order existing equations for an optical replay cycle.

    This deliberately changes only transmission order. Each bounded window
    sends its systematic symbols followed by interleaved repair equations with
    a reproducible per-cycle shuffle. The QFS1 equation masks and symbol
    identities remain untouched.
    """
    grouped: Dict[int, List[FECRecord]] = {}
    for record in records:
        grouped.setdefault(record.block_id, []).append(record)
    block_ids = sorted(grouped)
    if block_ids:
        shift = cycle % len(block_ids)
        block_ids = block_ids[shift:] + block_ids[:shift]
    ordered: List[FECRecord] = []
    window_blocks = max(1, int(window_blocks))
    for start in range(0, len(block_ids), window_blocks):
        window = block_ids[start:start + window_blocks]
        repairs: Dict[int, List[FECRecord]] = {}
        sources: Dict[int, List[FECRecord]] = {}
        for block_id in window:
            block = grouped[block_id]
            sources[block_id] = [record for record in block if record.symbol_index < record.source_count]
            if interleave_sources and cycle:
                random.Random(seed ^ ((block_id + 1) * 0x9E3779B1) ^ (cycle * 0x85EBCA77)).shuffle(sources[block_id])
            repair = [record for record in block if record.symbol_index >= record.source_count]
            random.Random(seed ^ ((block_id + 1) * 0x85EBCA77) ^ (cycle * 0xC2B2AE35)).shuffle(repair)
            repairs[block_id] = repair
        if interleave_sources:
            for offset in range(max((len(items) for items in sources.values()), default=0)):
                ordered.extend(sources[block_id][offset] for block_id in window if offset < len(sources[block_id]))
        else:
            for block_id in window:
                ordered.extend(sources[block_id])
        for offset in range(max((len(items) for items in repairs.values()), default=0)):
            ordered.extend(repairs[block_id][offset] for block_id in window
                           if offset < len(repairs[block_id]))
    return ordered


def _solve_equations(equations: Iterable[tuple[int, bytes]], k: int, symbol_size: int) -> Dict[int, bytes]:
    known: Dict[int, bytes] = {}
    pending = [(mask, bytearray(payload)) for mask, payload in equations if mask]
    # Peeling removes singleton equations cheaply and is the normal path.
    changed = True
    while changed:
        changed = False
        next_pending = []
        for mask, payload in pending:
            for index, value in known.items():
                if mask & (1 << index):
                    mask ^= 1 << index
                    _xor_into(payload, value)
            if mask and mask & (mask - 1) == 0:
                index = mask.bit_length() - 1
                if index not in known:
                    known[index] = bytes(payload)
                    changed = True
            elif mask:
                next_pending.append((mask, payload))
        pending = next_pending
    if len(known) == k:
        return known

    # Rank-recovery fallback for the small residual system.  All operations
    # are GF(2), so the packet payload is XORed alongside each row.
    pivots: Dict[int, tuple[int, bytearray]] = {}
    for mask, payload in pending:
        for index, value in known.items():
            if mask & (1 << index):
                mask ^= 1 << index
                _xor_into(payload, value)
        while mask:
            pivot = mask.bit_length() - 1
            previous = pivots.get(pivot)
            if previous is None:
                pivots[pivot] = (mask, payload)
                break
            mask ^= previous[0]
            _xor_into(payload, previous[1])
    for pivot in sorted(pivots, reverse=True):
        mask, payload = pivots[pivot]
        for index, value in known.items():
            if mask & (1 << index):
                mask ^= 1 << index
                _xor_into(payload, value)
        if mask and mask & (mask - 1) == 0:
            known[mask.bit_length() - 1] = bytes(payload)
    return known


def recover_symbols(records: Iterable[FECRecord], source_count: int, symbol_size: int,
                    file_size: int) -> bytes:
    by_block: Dict[int, List[FECRecord]] = {}
    for record in records:
        if record.source_count <= 0 or record.source_count > DEFAULT_BLOCK_SIZE:
            continue
        if record.mask == 0 or record.payload.__len__() != symbol_size:
            continue
        by_block.setdefault(record.block_id, []).append(record)
    recovered: List[bytes] = []
    expected_blocks = (source_count + DEFAULT_BLOCK_SIZE - 1) // DEFAULT_BLOCK_SIZE
    for block_id in range(expected_blocks):
        block_records = by_block.get(block_id, [])
        if not block_records:
            raise ValueError(f"missing FEC block {block_id}")
        k = block_records[0].source_count
        solved = _solve_equations(((record.mask, record.payload) for record in block_records), k, symbol_size)
        if len(solved) != k:
            raise ValueError(f"insufficient FEC symbols for block {block_id}: {len(solved)}/{k}")
        recovered.extend(solved[index] for index in range(k))
    return b"".join(recovered)[:file_size]
