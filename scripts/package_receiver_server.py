"""Create a Win10 receiver bundle without local keys or Python environments."""
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from build_standalone_receiver import build
from build_receiver_qr_vendor import build as build_qr_vendor

ROOT = Path(__file__).resolve().parents[1]


def package():
    build()
    build_qr_vendor()
    output = ROOT / "receiver-server-win10.zip"
    files = [
        "receiver-standalone.html", "receiver_server.py", "receiver_terminal_qr.py", "receiver-qr.zip", "start_receiver_server.cmd",
        "prepare_receiver_https.ps1", "docs/WIN10_RECEIVER_SERVER.md",
        "docs/THIRD_PARTY_NOTICES.md", "docs/MANUAL_REPAIR.md", "LICENSE",
    ]
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for name in files:
            archive.write(ROOT / name, name)
        archive.writestr("tools/README.txt", "Place the official Windows mkcert binary here as mkcert.exe.\nDownload: https://github.com/FiloSottile/mkcert/releases\nSee docs/WIN10_RECEIVER_SERVER.md for setup.\n")
        archive.writestr("START_HERE.txt", "Win10 receiver server for Safari (no iPhone app required).\n\n1. Install Python 3.10+. No pip dependencies required.\n2. Place the official mkcert Windows binary in tools/mkcert.exe or next to prepare_receiver_https.ps1 as mkcert.exe.\n3. Read docs/WIN10_RECEIVER_SERVER.md for LAN IP, HTTPS, firewall, and iPhone certificate trust setup.\n4. Generate the certificate ON THE SERVER PC. No private keys are included in this bundle.\n5. Start start_receiver_server.cmd --bootstrap-ca for initial iPhone setup.\n6. After the iPhone trusts the CA, restart without --bootstrap-ca.\n\nThe sender PC remains offline. Only the receiver server and iPhone need a LAN connection; internet access is not required at runtime.\n")
    print(f"Packaged {output} ({output.stat().st_size:,} bytes)")


if __name__ == "__main__":
    package()
