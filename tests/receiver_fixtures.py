"""Generate real QFS1 packets and QR images for the Node receiver tests."""

import base64
import hashlib
import json
import sys

from sender.protocol import TransferMetadata, encode_data, encode_meta, split_source_symbols
from sender.qr import packet_to_image


def base64_text(data):
    return base64.b64encode(data).decode("ascii")


def transfer(valid_digest):
    data = bytes((index * 31) & 255 for index in range(2501))
    symbols = split_source_symbols(data, 1200, 64)
    digest = hashlib.sha256(data).digest() if valid_digest else bytes(32)
    meta = TransferMetadata.new(
        "测试.zip", len(data), 1200, len(symbols), 64,
        bytes.fromhex("00112233445566778899aabbccddeeff"), sha256=digest,
    )
    packets = [encode_meta(meta)]
    packets.extend(encode_data(meta.session_id, symbol) for symbol in symbols)
    return {"packets": [base64_text(packet) for packet in packets], "bytes": base64_text(data)}


def dense_qr():
    data = bytes((index * 31 + 7) & 255 for index in range(1252))
    image = packet_to_image(data, box_size=4).convert("L")
    return {"bytes": base64_text(data), "side": image.width, "grayscale": base64_text(image.tobytes())}


if __name__ == "__main__":
    fixture = dense_qr() if sys.argv[1] == "qr" else transfer(sys.argv[1] == "valid")
    print(json.dumps(fixture))
