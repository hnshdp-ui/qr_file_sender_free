import itertools
import tempfile
import pytest

from sender import cli
from sender.bundle import cleanup_session
from sender.fec import recover_symbols
from sender.protocol import DATA, META, parse_packet
from sender.qr import packet_to_image


def test_folder_to_packets_and_qr_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    source = tmp_path / "source"
    source.mkdir()
    (source / "sample.bin").write_bytes(bytes(range(256)) * 20)
    _, archive, session_dir, _, meta, records, _ = cli.build_transfer(str(source))
    try:
        assert len(meta.session_id) == 16
        assert session_dir.name == meta.session_id.hex()
        # Include every data frame and the periodically repeated metadata frames.
        interval = 2
        count = 1 + len(records) + len(records) // interval
        packets = list(itertools.islice(cli._stream(meta, records, interval), count))
        decoded = [parse_packet(packet) for packet in packets]
        assert decoded[0] == (META, meta.session_id, meta)
        assert all(session == meta.session_id for _, session, _ in decoded)
        data = [record for kind, _, record in decoded if kind == DATA]
        assert len(data) == len(records)
        assert recover_symbols(data, meta.source_symbol_count, meta.symbol_size,
                               meta.file_size) == archive.read_bytes()
        for packet in (packets[0], packets[1]):
            image = packet_to_image(packet, box_size=1)
            assert image.size[0] == image.size[1] > 0
    finally:
        cleanup_session(session_dir)
    assert not session_dir.exists()


def test_no_display_advances_stream(tmp_path, monkeypatch):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    source = tmp_path / "source"
    source.mkdir()
    original_stream = cli._stream
    validated = []

    def checked_stream(*args):
        packet = next(original_stream(*args))
        validated.append(parse_packet(packet))
        yield packet

    monkeypatch.setattr(cli, "_stream", checked_stream)
    assert cli.main([str(source), "--no-display"]) == 0
    assert len(validated) == 1
    assert validated[0][0] == META
    assert not list((tmp_path / "qr_file_sender").iterdir())


def test_cycle_count_includes_the_final_periodic_meta():
    assert cli.qr_cycle_counts(4224, 24) == (4224, 177)
    assert cli.qr_cycle_counts(25, 24) == (25, 2)


def test_standard_stream_sends_all_blocks_sources_before_repairs():
    from sender.fec import encode_symbols
    from sender.protocol import TransferMetadata

    # 17 blocks exposes the old 16-block scheduling boundary without a large file.
    records, source_count, total = encode_symbols(bytes(range(34)), 1, block_size=2)
    meta = TransferMetadata.new("order.zip", 34, 1, source_count, total, 2)
    stream = cli._stream(meta, records, 24)
    data = []
    while len(data) < total:
        kind, _, payload = parse_packet(next(stream))
        if kind == DATA:
            data.append(payload)
    assert len(data[:source_count]) == 34
    assert all(record.symbol_index < record.source_count for record in data[:source_count])
    assert {record.block_id for record in data[:source_count]} == set(range(17))
    assert set(data) == set(records)
    assert [record.block_id for record in data[:17]] == list(range(17))


def test_seek_and_select_keep_original_packet_identity():
    from sender.fec import encode_symbols
    from sender.protocol import TransferMetadata, encode_data, encode_meta
    records, count, total = encode_symbols(bytes(range(10)), 1, block_size=4)
    meta = TransferMetadata.new("repair.zip", 10, 1, count, total, 4)
    sources = {r.block_id * 4 + r.symbol_index + 1: encode_data(meta.session_id, r)
               for r in records if r.symbol_index < r.source_count}
    seek = cli._stream(meta, records, 24, start_number=8)
    assert next(seek) == encode_meta(meta)
    assert [next(seek) for _ in range(3)] == [sources[n] for n in [8, 9, 10]]
    selected = cli._stream(meta, records, 24, selected_numbers=[0, 9, 2])
    assert list(itertools.islice(selected, 6)) == [encode_meta(meta), sources[9], sources[2]] * 2
    assert list(itertools.islice(cli._stream(meta, records, 24, selected_numbers=[0]), 3)) == [encode_meta(meta)] * 3


def test_repair_number_parser():
    from sender.playback import parse_numbers
    assert parse_numbers("0,12,35-38，12", 100) == [0, 12, 35, 36, 37, 38]
    for invalid in ["", "-1", "101", "5-3", "B1/S2", "0-999999999"]:
        with pytest.raises(ValueError):
            parse_numbers(invalid, 100)
