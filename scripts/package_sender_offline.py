"""Bundle sender sources and already downloaded wheels for this Windows Python."""
import platform
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]


def package():
    wheels = sorted((ROOT / "wheelhouse").glob("*.whl"))
    if sys.platform != "win32" or not wheels:
        raise RuntimeError("Prepare wheelhouse for the target Windows Python before packaging")
    tag = f"py{sys.version_info.major}{sys.version_info.minor}"
    architecture = "win64" if platform.machine().upper() in ("AMD64", "X86_64") else platform.machine().lower()
    output = ROOT / f"sender-offline-{architecture}-{tag}.zip"
    names = ["requirements.txt", "pyproject.toml", "setup_sender.cmd", "setup_sender_offline.cmd",
             "run_sender.cmd", "LICENSE", "docs/MANUAL_REPAIR.md"]
    files = [ROOT / name for name in names] + sorted((ROOT / "sender").rglob("*.py")) + wheels
    if (ROOT / "wheelhouse/TARGET.txt").exists(): files.append(ROOT / "wheelhouse/TARGET.txt")
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for path in files: archive.write(path, path.relative_to(ROOT).as_posix())
        archive.writestr("START_HERE.txt", f"Offline sender: Windows {architecture}, Python {sys.version_info.major}.{sys.version_info.minor}.\n"
            "Python must already be installed; the Python installer is not included.\n"
            "1. Extract this archive into a new folder.\n"
            "2. Run setup_sender_offline.cmd (uses local wheels only).\n"
            "3. Run run_sender.cmd and check that QR encoder is ZXing-C++ native.\n"
            "For other Python versions or CPU architectures, regenerate wheelhouse on a preparation PC.\n"
            "No virtual environments, certificates, private keys, or user transfer files are included.\n")
    print(f"Packaged {output} ({output.stat().st_size:,} bytes)")


if __name__ == "__main__": package()
