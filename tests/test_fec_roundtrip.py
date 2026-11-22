import random

import pytest

from sender.fec import encode_symbols, recover_symbols, schedule_records


@pytest.mark.parametrize("size", [96 * 1024, 1_000_000, 3_000_000, 5_000_000, 10_000_000])
@pytest.mark.parametrize("loss", [0.0, 0.05, 0.10, 0.20, 0.30])
def test_fec_roundtrip_under_deterministic_loss(size, loss):
    data = bytes((index * 31 + 7) % 256 for index in range(size))
    records, source_count, _ = encode_symbols(data, 1200, overhead=4.0)
    rng = random.Random(20260808 + size + round(loss * 100))
    kept = [record for record in records if rng.random() >= loss]
    recovered = recover_symbols(kept, source_count, 1200, len(data))
    assert recovered == data


def test_scheduler_is_systematic_first_and_changes_replay_order_without_changing_records():
    data = bytes((index * 13 + 5) % 256 for index in range(3_000))
    records, _, _ = encode_symbols(data, 1200, block_size=2, overhead=4.0)
    first = schedule_records(records, cycle=0, seed=17)
    second = schedule_records(records, cycle=1, seed=17)
    first_repair = next(index for index, record in enumerate(first) if record.symbol_index >= record.source_count)
    assert all(record.symbol_index < record.source_count for record in first[:first_repair])
    assert {record for record in first} == {record for record in second}
    assert first != second
