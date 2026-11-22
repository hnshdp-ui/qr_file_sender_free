from __future__ import annotations

import fnmatch
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Union


DEFAULT_EXCLUDES = ("Thumbs.db", "desktop.ini", "~$*", "*.tmp")


@dataclass(frozen=True)
class ScanEntry:
    absolute: Path
    relative: str
    is_dir: bool
    size: int = 0


@dataclass(frozen=True)
class ScanResult:
    source: Path
    entries: List[ScanEntry]
    excluded: List[str]
    total_size: int

    @property
    def files(self) -> int:
        return sum(not entry.is_dir for entry in self.entries)

    @property
    def folders(self) -> int:
        return sum(entry.is_dir for entry in self.entries)


def is_excluded(name: str, patterns: Iterable[str] = DEFAULT_EXCLUDES) -> bool:
    return any(fnmatch.fnmatchcase(name, pattern) for pattern in patterns)


def scan_folder(path: Union[str, os.PathLike], patterns: Iterable[str] = DEFAULT_EXCLUDES) -> ScanResult:
    source = Path(path).expanduser()
    if not source.exists():
        raise ValueError(f"Folder does not exist: {source}")
    if not source.is_dir():
        raise ValueError(f"Path is not a directory: {source}")
    if not os.access(source, os.R_OK):
        raise ValueError(f"Folder is not readable: {source}")

    entries: List[ScanEntry] = []
    excluded: List[str] = []
    total_size = 0
    for root, dirs, files in os.walk(source, topdown=True, followlinks=False):
        root_path = Path(root)
        kept_dirs = []
        for directory in sorted(dirs):
            if is_excluded(directory, patterns):
                excluded.append(str((root_path / directory).relative_to(source)))
            else:
                kept_dirs.append(directory)
                rel = (root_path / directory).relative_to(source).as_posix() + "/"
                entries.append(ScanEntry(root_path / directory, rel, True))
        dirs[:] = kept_dirs
        for filename in sorted(files):
            absolute = root_path / filename
            if is_excluded(filename, patterns):
                excluded.append(str(absolute.relative_to(source)))
                continue
            if not absolute.is_file():
                continue
            try:
                size = absolute.stat().st_size
                with absolute.open("rb") as handle:
                    handle.read(1)
            except OSError as exc:
                raise ValueError(f"File is not readable: {absolute}") from exc
            entries.append(ScanEntry(absolute, absolute.relative_to(source).as_posix(), False, size))
            total_size += size
    return ScanResult(source, entries, excluded, total_size)
