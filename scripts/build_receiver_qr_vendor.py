"""Bundle the installed qrcode sources for a receiver with no pip setup."""
from importlib.metadata import distribution
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]


def build():
    package = distribution("qrcode")
    if package.version != "8.2":
        raise RuntimeError("Build the receiver QR bundle with qrcode 8.2")
    output = ROOT / "receiver-qr.zip"
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for entry in sorted(package.files, key=str):
            name = entry.as_posix()
            if name.startswith("qrcode/") and name.endswith(".py"):
                target = name
            elif name.endswith(".dist-info/LICENSE"):
                target = "qrcode-LICENSE.txt"
            else:
                continue
            info = ZipInfo(target, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            archive.writestr(info, package.locate_file(entry).read_bytes())
        archive.writestr("README.txt", "python-qrcode 8.2, BSD license. Sources bundled unchanged.\n"
                         "https://github.com/lincolnloop/python-qrcode\n"
                         "Only QR matrix generation is used; Pillow and PyPNG are not required.\n")
    print(f"Built {output} ({output.stat().st_size:,} bytes)")


if __name__ == "__main__":
    build()
