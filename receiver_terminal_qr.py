"""Print a QR link in Windows terminals using the bundled pure-Python encoder."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def qr_matrix(url: str):
    bundle = str(Path(__file__).with_name("receiver-qr.zip"))
    sys.path.insert(0, bundle)
    try:
        import qrcode
        code = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=4)
        code.add_data(url)
        code.make(fit=True)
        return code.get_matrix()
    finally:
        sys.path.remove(bundle)


def render_terminal_qr(url: str, color: bool = True) -> str:
    matrix = qr_matrix(url)
    width = len(matrix)
    # Each character is one module wide and two modules high. Explicit black
    # on white colors keep dark terminal themes from inverting the QR.
    glyphs = {(False, False): " ", (True, False): "▀", (False, True): "▄", (True, True): "█"}
    lines = []
    for row in range(0, width, 2):
        top = matrix[row]
        bottom = matrix[row + 1] if row + 1 < width else [False] * width
        line = "".join(glyphs[bool(a), bool(b)] for a, b in zip(top, bottom))
        lines.append(("\x1b[30;107m" + line + "\x1b[0m") if color else line)
    return "\n".join(lines)


def enable_terminal_color(output) -> bool:
    if not output.isatty():
        return False
    if os.name != "nt":
        return True
    try:
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetStdHandle.argtypes = [wintypes.DWORD]
        kernel.GetStdHandle.restype = wintypes.HANDLE
        kernel.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        handle = kernel.GetStdHandle(-11)
        mode = wintypes.DWORD()
        return bool(kernel.GetConsoleMode(handle, ctypes.byref(mode)) and
                    kernel.SetConsoleMode(handle, mode.value | 0x0004))
    except (OSError, AttributeError):
        return False


def print_receiver_qr(url: str, output=None):
    output = sys.stdout if output is None else output
    print("Scan with the iPhone camera to open the receiver:", file=output)
    print(render_terminal_qr(url, color=enable_terminal_color(output)), file=output)
    print(url, file=output, flush=True)
