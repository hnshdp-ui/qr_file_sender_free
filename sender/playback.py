"""QR playback timing and stable repair numbers (META=0, sources=1..N)."""
from __future__ import annotations

import re


def next_frame_deadline(previous: float, now: float, interval: float) -> float:
    """Carry small timer delays forward; rebase after a full missed interval.

    Rebasing after a long stall avoids a burst of catch-up frames. Packets
    remain in order: this changes display timing, never skips source data.
    """
    deadline = previous + interval
    return deadline if deadline > now else now + interval


def parse_numbers(value: str, source_count: int) -> list[int]:
    numbers = []
    seen = set()
    for item in re.split(r"[,，;；\s]+", value.strip()):
        if not item:
            continue
        match = re.fullmatch(r"(\d+)(?:-(\d+))?", item)
        if not match:
            raise ValueError("请输入编号或范围，例如 0,12,35-38")
        first = int(match[1])
        last = int(match[2]) if match[2] is not None else first
        if not 0 <= first <= last <= source_count:
            raise ValueError(f"编号范围为 0～{source_count}；0 是文件信息帧")
        for number in range(first, last + 1):
            if number not in seen:
                seen.add(number)
                numbers.append(number)
    if not numbers:
        raise ValueError("请先输入编号")
    return numbers
