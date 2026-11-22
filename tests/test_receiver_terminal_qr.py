import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from receiver_terminal_qr import render_terminal_qr


@pytest.mark.parametrize("url", ["https://192.168.31.191:8443/", "https://192.168.1.50:9443/"])
def test_printed_terminal_modules_decode_to_receiver_url(url):
    from PIL import Image
    import zxingcpp

    rendered = render_terminal_qr(url)
    lines = re.sub(r"\x1b\[[0-9;]*m", "", rendered).splitlines()
    glyphs = {" ": (255, 255), "▀": (0, 255), "▄": (255, 0), "█": (0, 0)}
    image = Image.new("L", (len(lines[0]), len(lines) * 2), 255)
    for y, line in enumerate(lines):
        for x, glyph in enumerate(line):
            upper, lower = glyphs[glyph]
            image.putpixel((x, 2 * y), upper)
            image.putpixel((x, 2 * y + 1), lower)
    image = image.resize((image.width * 8, image.height * 8), Image.Resampling.NEAREST)
    decoded = zxingcpp.read_barcode(image)
    assert decoded is not None
    assert decoded.text == url


def test_receiver_qr_works_without_site_packages():
    root = Path(__file__).parents[1]
    result = subprocess.run([sys.executable, "-S", "-c",
        "import json; from receiver_terminal_qr import qr_matrix; "
        "matrix = qr_matrix('https://192.168.31.191:8443/'); import qrcode; "
        "print(json.dumps({'size': len(matrix), 'origin': qrcode.__file__}))"],
        cwd=root, text=True, encoding="utf-8", capture_output=True, check=True)
    data = json.loads(result.stdout)
    assert data["size"] >= 29
    assert "receiver-qr.zip" in data["origin"]


@pytest.mark.parametrize("show_qr", [True, False])
def test_server_startup_uses_configured_address_and_actual_port(tmp_path, monkeypatch, capsys, show_qr):
    import receiver_server

    (tmp_path / "certs").mkdir()
    (tmp_path / "certs/server-address.txt").write_text("192.168.31.191\n", encoding="utf-8")

    class Server:
        server_port = 9443

        def serve_forever(self):
            raise KeyboardInterrupt

        def server_close(self):
            pass

    monkeypatch.setattr(receiver_server, "ROOT", tmp_path)
    monkeypatch.setattr(receiver_server, "make_https_server", lambda *_args: Server())
    assert receiver_server.main([] if show_qr else ["--no-terminal-qr"]) == 0
    output = capsys.readouterr().out
    assert "https://192.168.31.191:9443/" in output
    assert ("Scan with the iPhone camera" in output) == show_qr
    assert ("█" in output) == show_qr
