import itertools
import tempfile
import pytest

from sender import cli
from sender.bundle import cleanup_session
from sender.protocol import DATA, META, TransferMetadata, encode_data, encode_meta, parse_packet, split_source_symbols
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
        assert data == records
        assert len(data) == meta.source_symbol_count
        assert b"".join(symbol.payload for symbol in data)[:meta.file_size] == archive.read_bytes()
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


@pytest.mark.parametrize(("encoder", "ecc", "symbol_size"), [
    ("zxing", "L", 2899), ("zxing", "M", 2277),
    ("zxing", "Q", 1609), ("zxing", "H", 1219),
    ("qrcode", "L", 2901), ("qrcode", "M", 2279),
    ("qrcode", "Q", 1611), ("qrcode", "H", 1221),
])
def test_oversized_symbols_are_capped_before_qr_playback(
        tmp_path, monkeypatch, capsys, encoder, ecc, symbol_size):
    from sender import display

    source = tmp_path / "source"
    source.mkdir()
    (source / "sample.bin").write_bytes(bytes(range(256)))
    observed = []

    def inspect(stream, _title, fps, *_args, stream_factory, **kwargs):
        assert fps == 12
        assert kwargs["encoder"] == encoder
        assert kwargs["ecc"] == ecc
        meta_packet, source_packet = next(stream), next(stream)
        assert parse_packet(meta_packet)[2].symbol_size == symbol_size
        assert len(parse_packet(source_packet)[2].payload) == symbol_size
        assert list(itertools.islice(stream_factory(None, [1]), 2)) == [meta_packet, source_packet]
        for packet in (meta_packet, source_packet):
            image = packet_to_image(packet, box_size=1, encoder=encoder, ecc=ecc)
            assert image.size[0] == image.size[1] > 0
        observed.append(True)

    monkeypatch.setattr(display, "show_animated_qr", inspect)
    requested_encoder = "auto" if encoder == "zxing" and ecc == "L" else encoder
    assert cli.main([str(source), "--fps", "12", "--symbol-size", "3000",
                     "--qr-ecc", ecc, "--qr-encoder", requested_encoder]) == 0
    assert observed
    assert f"Using {symbol_size} bytes per symbol." in capsys.readouterr().err


def test_cycle_count_includes_the_final_periodic_meta():
    assert cli.qr_cycle_counts(4224, 24) == (4224, 177)
    assert cli.qr_cycle_counts(25, 24) == (25, 2)


def test_window_stream_replays_originals_and_supports_manual_resend(tmp_path, monkeypatch):
    from sender import display

    source = tmp_path / "source"
    source.mkdir()
    (source / "sample.bin").write_bytes(bytes(range(256)))
    observed = []

    def inspect(stream, *_args, cycle_frames, stream_factory, ecc, **_kwargs):
        assert ecc == "M"
        def decode_cycle(packets, count):
            return [parse_packet(packet) for packet in itertools.islice(packets, count)]

        first = decode_cycle(stream, cycle_frames)
        second = decode_cycle(stream, cycle_frames)
        seek = decode_cycle(stream_factory(2, None), cycle_frames)
        manual = decode_cycle(stream_factory(None, [2]), 4)
        observed.append((first, second, seek, manual))

    monkeypatch.setattr(display, "show_animated_qr", inspect)
    assert cli.main([str(source), "--symbol-size", "128", "--meta-interval", "2", "--qr-ecc", "m"]) == 0
    first, second, seek, manual = observed[0]
    assert first[0] == second[0] == seek[0] == manual[0]
    originals = [record for kind, _, record in first if kind == DATA]
    assert len(originals) == first[0][2].source_symbol_count
    assert second == first
    assert seek[1] == manual[1] == manual[3]
    assert manual[0] == manual[2]


def test_standard_stream_plays_sources_in_number_order_on_every_cycle():
    data = bytes(range(35))
    sources = split_source_symbols(data, 1, block_size=2)
    meta = TransferMetadata.new("order.zip", len(data), 1, len(sources), 2)
    count = sum(cli.qr_cycle_counts(len(sources), 24))
    stream = cli._stream(meta, sources, 24)
    for _ in range(2):
        packets = [parse_packet(packet) for packet in itertools.islice(stream, count)]
        assert packets[0][0] == packets[25][0] == META
        symbols = [record for kind, _, record in packets if kind == DATA]
        assert symbols == sources
        assert b"".join(symbol.payload for symbol in symbols) == data


def test_seek_and_select_keep_original_packet_identity():
    records = split_source_symbols(bytes(range(10)), 1, block_size=4)
    meta = TransferMetadata.new("repair.zip", 10, 1, len(records), 4)
    sources = {r.block_id * 4 + r.symbol_index + 1: encode_data(meta.session_id, r) for r in records}
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
