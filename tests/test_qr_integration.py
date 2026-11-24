import pytest
import base64
import json
import subprocess
from pathlib import Path

from scripts.build_standalone_receiver import build
from sender.protocol import SourceSymbol, TransferMetadata, encode_data, encode_meta, parse_packet
from sender.qr import packet_to_image


@pytest.fixture(scope="module")
def receiver_page(tmp_path_factory):
    output = tmp_path_factory.mktemp("pages") / "index.html"
    build(output)
    return output


def test_qr_encoder_accepts_binary_packet():
    pytest.importorskip("qrcode")
    meta = TransferMetadata.new("sample.zip", 42, 1200, 1, 64, bytes(range(16)))
    image = packet_to_image(encode_meta(meta), box_size=2)
    assert image.size[0] == image.size[1]
    assert parse_packet(encode_meta(meta))[2].filename == "sample.zip"


@pytest.mark.parametrize("encoder", ["zxing", "qrcode"])
@pytest.mark.parametrize("zero_payload", [False, True])
def test_qr_image_roundtrip_through_vendored_jsqr(zero_payload, encoder):
    pytest.importorskip("qrcode")
    meta = TransferMetadata.new("sample.zip", 42, 1200, 1, 64, bytes(range(16)))
    packet = encode_meta(meta)
    if zero_payload:
        packet = encode_data(meta.session_id, SourceSymbol(0, 0, 1, bytes(1200)))
    image = packet_to_image(packet, box_size=3, encoder=encoder).convert("RGBA")
    request = json.dumps({
        "width": image.width,
        "height": image.height,
        "rgba": base64.b64encode(image.tobytes()).decode("ascii"),
    })
    result = subprocess.run(
        ["node", str(__file__).replace("test_qr_integration.py", "decode_qr.mjs")],
        input=request,
        text=True,
        capture_output=True,
        check=True,
    )
    decoded = base64.b64decode(result.stdout)
    assert decoded == packet


@pytest.mark.parametrize("size", [1200, 1800, 2400])
@pytest.mark.parametrize("disable_wasm", [False, True])
@pytest.mark.parametrize("zero_payload", [False, True])
def test_native_encoder_roundtrips_through_embedded_receiver(size, disable_wasm, zero_payload, receiver_page):
    from sender.qr import select_encoder

    assert select_encoder() == "zxing"
    payload = bytes(size) if zero_payload else bytes((i * 73 + (i >> 4) * 29) & 255 for i in range(size))
    packet = encode_data(bytes(range(16)), SourceSymbol(0, 0, 1, payload))
    image = packet_to_image(packet, box_size=4).convert("RGBA")
    request = json.dumps({"width": image.width, "height": image.height,
                          "rgba": base64.b64encode(image.tobytes()).decode(),
                          "disableWasm": disable_wasm})
    decoder = Path(__file__).with_name("decode_standalone_worker.mjs")
    result = subprocess.run(["node", str(decoder), str(receiver_page)],
                            input=request, text=True, capture_output=True, check=True)
    decoded = json.loads(result.stdout)
    assert base64.b64decode(decoded["binary"]) == packet
    assert decoded["readyDecoder"] == ("JSQR" if disable_wasm else "ZXING-WASM")
    assert decoded["location"] is not None


def test_auto_encoder_can_fall_back_when_native_library_is_missing(monkeypatch):
    import sys
    from sender.qr import select_encoder

    monkeypatch.setitem(sys.modules, "zxingcpp", None)
    assert select_encoder() == "qrcode"
    with pytest.raises(RuntimeError, match="zxing-cpp"):
        select_encoder("zxing")
