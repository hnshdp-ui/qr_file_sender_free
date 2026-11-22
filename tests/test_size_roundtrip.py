import os
import random

import pytest

from sender.config import MAX_ZIP_SIZE, SYMBOL_SIZE, BLOCK_SIZE, FEC_OVERHEAD, classify_zip_size
from sender.fec import encode_symbols, recover_symbols


@pytest.mark.skipif(os.environ.get("QFS_RUN_SIZE_BENCHMARK") != "1", reason="large local benchmark")
@pytest.mark.parametrize("size", [20 * 1024 * 1024, 30 * 1024 * 1024])
def test_large_roundtrip(size):
    data = bytes((index * 29 + 17) % 256 for index in range(size))
    policy = classify_zip_size(size)
    assert policy.size <= MAX_ZIP_SIZE
    records, source_count, _ = encode_symbols(data, SYMBOL_SIZE, BLOCK_SIZE, FEC_OVERHEAD)
    reconstructed = recover_symbols(records, source_count, SYMBOL_SIZE, len(data))
    assert reconstructed == data


@pytest.mark.skipif(os.environ.get("QFS_RUN_30MB_LOSS") != "1", reason="large loss benchmark")
def test_30mb_roundtrip_with_five_percent_loss():
    size = 30 * 1024 * 1024
    data = bytes((index * 29 + 17) % 256 for index in range(size))
    records, source_count, _ = encode_symbols(data, SYMBOL_SIZE, BLOCK_SIZE, FEC_OVERHEAD)
    rng = random.Random(3005)
    kept = [record for record in records if rng.random() >= 0.05]
    reconstructed = recover_symbols(kept, source_count, SYMBOL_SIZE, len(data))
    assert reconstructed == data
