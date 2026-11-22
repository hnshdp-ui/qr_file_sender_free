from __future__ import annotations

from typing import Any

from .config import QR_ECC


def select_encoder(requested: str = "auto") -> str:
    if requested not in ("auto", "zxing", "qrcode"):
        raise ValueError("QR encoder must be auto, zxing, or qrcode")
    if requested != "qrcode":
        try:
            import zxingcpp
            if not hasattr(zxingcpp, "create_barcode"):
                raise ImportError("ZXing-C++ 3.x is required")
            return "zxing"
        except ImportError as exc:
            if requested == "zxing":
                raise RuntimeError("Native QR encoding requires zxing-cpp; run setup_sender.cmd") from exc
    return "qrcode"


def _native_image(packet: bytes, box_size: int, border: int, ecc: str):
    import zxingcpp
    from PIL import Image, ImageOps

    barcode = zxingcpp.create_barcode(packet, zxingcpp.BarcodeFormat.QRCode, ec_level=ecc.upper())
    bitmap = barcode.to_image(scale=1, add_quiet_zones=False)
    height, width = memoryview(bitmap).shape
    image = Image.frombuffer("L", (width, height), bitmap, "raw", "L", 0, 1).copy()
    image = ImageOps.expand(image, border=border, fill=255)
    if box_size != 1:
        image = image.resize((image.width * box_size, image.height * box_size), Image.Resampling.NEAREST)
    return image


def _zero_safe_codewords(code):
    """Encode zero RS blocks directly; qrcode 8.2 calls glog(0) for these."""
    from qrcode import base, util

    buffer = util.BitBuffer()
    for data in code.data_list:
        buffer.put(data.mode, 4)
        buffer.put(len(data), util.length_in_bits(data.mode, code.version))
        data.write(buffer)
    blocks = base.rs_blocks(code.version, code.error_correction)
    bit_limit = sum(block.data_count * 8 for block in blocks)
    for _ in range(min(4, bit_limit - len(buffer))):
        buffer.put_bit(False)
    while len(buffer) % 8:
        buffer.put_bit(False)
    for i in range((bit_limit - len(buffer)) // 8):
        buffer.put(util.PAD0 if i % 2 == 0 else util.PAD1, 8)

    data_blocks, parity_blocks = [], []
    offset = 0
    for block in blocks:
        data = buffer.buffer[offset:offset + block.data_count]
        offset += block.data_count
        if any(data):
            single = util.BitBuffer()
            single.buffer = data
            single.length = len(data) * 8
            encoded = util.create_bytes(single, [block])
            parity = encoded[block.data_count:]
        else:
            # A zero polynomial has zero Reed-Solomon parity at every degree.
            parity = [0] * (block.total_count - block.data_count)
        data_blocks.append(data)
        parity_blocks.append(parity)
    return [block[i] for group in (data_blocks, parity_blocks)
            for i in range(max(map(len, group))) for block in group if i < len(block)]


def _build_code(packet: bytes, box_size: int, border: int, ecc: str):
    import qrcode
    from qrcode.constants import ERROR_CORRECT_H, ERROR_CORRECT_L, ERROR_CORRECT_M, ERROR_CORRECT_Q
    from qrcode.util import MODE_8BIT_BYTE, QRData

    error_correction = {"L": ERROR_CORRECT_L, "M": ERROR_CORRECT_M,
                        "Q": ERROR_CORRECT_Q, "H": ERROR_CORRECT_H}[ecc.upper()]
    code = qrcode.QRCode(version=None, error_correction=error_correction,
                         box_size=box_size, border=border)
    code.add_data(QRData(packet, mode=MODE_8BIT_BYTE), optimize=0)
    try:
        code.make(fit=True)
    except ValueError as exc:
        if str(exc) != "glog(0)":
            raise
        code.data_cache = _zero_safe_codewords(code)
        code.make(fit=False)
    return code


def packet_to_image(packet: bytes, box_size: int = 4, border: int = 4, ecc: str = QR_ECC, encoder: str = "auto") -> Any:
    if box_size < 1 or border < 0 or ecc.upper() not in ("L", "M", "Q", "H"):
        raise ValueError("Invalid QR size, border, or error correction level")
    if select_encoder(encoder) == "zxing":
        return _native_image(packet, box_size, border, ecc)
    try:
        code = _build_code(packet, box_size=box_size, border=border, ecc=ecc)
    except ImportError as exc:
        raise RuntimeError("QR rendering requires dependencies; run setup_sender.cmd") from exc
    return code.make_image(fill_color="black", back_color="white")
