from __future__ import annotations

import re
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from .folder_scan import ScanResult


SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def safe_zip_name(source_name: str, now: Optional[datetime] = None) -> str:
    stamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
    clean = SAFE_NAME.sub("_", source_name).strip("._-") or "Transfer"
    return f"{clean}_{stamp}.zip"


def create_zip(scan: ScanResult, session_id: str, temp_root: Optional[Path] = None) -> tuple[Path, Path]:
    base = Path(temp_root) if temp_root else Path(tempfile.gettempdir())
    session_dir = base / "qr_file_sender" / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    archive = session_dir / safe_zip_name(scan.source.name)
    try:
        with ZipFile(archive, "w", compression=ZIP_DEFLATED, allowZip64=True) as output:
            for entry in scan.entries:
                if entry.is_dir:
                    info = ZipInfo(entry.relative)
                    info.external_attr = 0o755 << 16
                    output.writestr(info, b"")
                else:
                    output.write(entry.absolute, entry.relative)
    except Exception:
        shutil.rmtree(session_dir, ignore_errors=True)
        raise
    return archive, session_dir


def cleanup_session(session_dir: Path) -> None:
    shutil.rmtree(session_dir, ignore_errors=True)
