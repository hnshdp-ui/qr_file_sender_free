import pytest

from sender.protocol import DATA, META, SourceSymbol, TransferMetadata, encode_data, encode_meta, parse_packet, split_source_symbols


@pytest.mark.parametrize("session", [b"", bytes(8), bytes(15), bytes(17)])
def test_metadata_rejects_invalid_session_before_streaming(session):
    with pytest.raises(ValueError, match="session_id must be 16 bytes"):
        TransferMetadata.new("sample.zip", 42, 1200, 1, 64, session)


def test_meta_and_data_roundtrip_and_crc_rejection():
    session = bytes(range(16))
    meta = TransferMetadata.new("テスト.zip", 1234, 1200, 2, 64, session)
    packet_type, parsed_session, parsed = parse_packet(encode_meta(meta))
    assert packet_type == META and parsed_session == session
    assert parsed.filename == "テスト.zip"
    record = SourceSymbol(0, 0, 2, b"payload")
    data_packet = encode_data(session, record)
    packet_type, parsed_session, parsed = parse_packet(data_packet)
    assert packet_type == DATA and parsed_session == session and parsed == record
    corrupted = bytearray(data_packet)
    corrupted[-1] ^= 0x80
    with pytest.raises(ValueError, match="CRC"):
        parse_packet(bytes(corrupted))


def test_source_symbols_preserve_block_positions_and_pad_the_final_symbol():
    assert split_source_symbols(b"abcde", 2, 2) == [
        SourceSymbol(0, 0, 2, b"ab"),
        SourceSymbol(0, 1, 2, b"cd"),
        SourceSymbol(1, 0, 1, b"e\0"),
    ]
