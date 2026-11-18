"""
Records which output files a run actually created, so the completion
message can show (and open) exactly what was written.
"""
from __future__ import annotations

from pathlib import Path

_written: list[Path] = []


def reset() -> None:
    _written.clear()


def record(path: Path) -> None:
    path = Path(path)
    if path not in _written:
        _written.append(path)


def written() -> list[Path]:
    return list(_written)
