import os

import pytest

from sender.fec import FECRecord, encode_symbols, recover_symbols
from sender.protocol import DATA, META, TransferMetadata, encode_data, encode_meta, parse_packet


@pytest.mark.parametrize("session", [b"", bytes(8), bytes(15), bytes(17)])
def test_metadata_rejects_invalid_session_before_streaming(session):
    with pytest.raises(ValueError, match="session_id must be 16 bytes"):
        TransferMetadata.new("sample.zip", 42, 1200, 1, 2, 64, session)


def test_meta_and_data_roundtrip_and_crc_rejection():
    session = bytes(range(16))
    meta = TransferMetadata.new("テスト.zip", 1234, 1200, 3, 6, 64, session)
    packet_type, parsed_session, parsed = parse_packet(encode_meta(meta))
    assert packet_type == META and parsed_session == session
    assert parsed.filename == "テスト.zip"
    record = FECRecord(0, 0, 2, 4, 1, b"payload")
    data_packet = encode_data(session, record)
    packet_type, parsed_session, parsed = parse_packet(data_packet)
    assert packet_type == DATA and parsed_session == session and parsed == record
    corrupted = bytearray(data_packet)
    corrupted[-1] ^= 0x80
    with pytest.raises(ValueError, match="CRC"):
        parse_packet(bytes(corrupted))


def test_duplicates_out_of_order_and_wrong_session_are_typed():
    data = b"A" * 10000
    records, source_count, _ = encode_symbols(data, 120, 64, 2.0)
    shuffled = list(reversed(records)) + [records[0], records[1]]
    assert recover_symbols(shuffled, source_count, 120, len(data)) == data
    assert parse_packet(encode_data(os.urandom(16), records[0]))[1] != bytes(range(16))
