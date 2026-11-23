import os

import pytest

from sender.config import MAX_ZIP_SIZE, SYMBOL_SIZE, BLOCK_SIZE, classify_zip_size
from sender.protocol import split_source_symbols


@pytest.mark.skipif(os.environ.get("QFS_RUN_SIZE_BENCHMARK") != "1", reason="large local benchmark")
@pytest.mark.parametrize("size", [20 * 1024 * 1024, MAX_ZIP_SIZE])
def test_large_roundtrip(size):
    data = (bytes(range(256)) * ((size + 255) // 256))[:size]
    policy = classify_zip_size(size)
    assert policy.size <= MAX_ZIP_SIZE
    symbols = split_source_symbols(data, SYMBOL_SIZE, BLOCK_SIZE)
    assert b"".join(symbol.payload for symbol in symbols)[:size] == data
