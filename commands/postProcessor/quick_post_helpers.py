"""
Pure helpers behind the one-click "Post Combined" command and the
dialog's quality-of-life defaults. Nothing in here imports ``adsk`` so it
can be unit tested outside Fusion.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Optional, Sequence


def is_usable_program(program) -> bool:
    """Same filter the NC Program dropdown uses."""
    return not (program.hasError or program.isEmpty or program.isSuppressed)


def pick_default_program(programs: Iterable, saved_name: Optional[str]):
    """
    Choose the NC Program to preselect.

    1. The program saved in the document settings, if it is still usable.
    2. Otherwise the first usable program that has a post processor.
    3. Otherwise the first usable program (the dialog then explains that a
       post processor is missing).

    Returns ``None`` when the document has no usable NC Program.
    """
    usable = [p for p in programs if is_usable_program(p)]
    if saved_name:
        for program in usable:
            if program.name == saved_name:
                return program
    for program in usable:
        if program.hasPostProcessor:
            return program
    return usable[0] if usable else None


def combined_output_path(folder, file_name: str, extension: Optional[str]) -> Path:
    """
    Path of the single combined file, built exactly the way
    ``OperationsHeader.WriteFirstHeaderStart`` builds it, so an existence
    check before posting matches the file that will be written.
    """
    return Path(folder) / f"{file_name}{extension or ''}"


def unique_paths(paths: Iterable[Path]) -> list[Path]:
    """De-duplicate while keeping first-seen order."""
    seen = set()
    out: list[Path] = []
    for path in paths:
        key = str(path)
        if key not in seen:
            seen.add(key)
            out.append(Path(path))
    return out


def common_folder(paths: Sequence[Path]) -> Optional[Path]:
    """Deepest folder containing every written file (None if no files)."""
    if not paths:
        return None
    parents = [str(Path(p).parent) for p in paths]
    try:
        return Path(os.path.commonpath(parents))
    except ValueError:  # different drives on Windows
        return Path(parents[0])


def describe_outputs(paths: Sequence[Path], limit: int = 8) -> str:
    """Human-readable list of written files for the completion message."""
    names = [Path(p).name for p in paths]
    shown = names[:limit]
    text = "<br>".join(shown)
    if len(names) > limit:
        text += f"<br>… and {len(names) - limit} more"
    return text


def open_in_file_browser(path: Path, platform: str = sys.platform) -> bool:
    """Open ``path`` in Explorer / Finder. Returns False if it could not."""
    try:
        if platform.startswith("win"):
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
        return True
    except Exception:
        return False


def program_file_name(document_name: str) -> str:
    """'Bracket v12' -> 'Bracket' (Fusion appends the version to doc names)."""
    import re
    name = re.sub(r"\s+v\d+$", "", (document_name or "").strip())
    return name or "program"


def join_target(folder, name: str, path_cls=Path) -> str:
    """Text for the File field: folder + name, no extension."""
    return str(path_cls(folder) / name) if folder else name


def split_target(text: str, extension: str | None, sanitize, path_cls=Path) -> tuple:
    """
    Parse the File field into (folder, name, error).

    Accepts quotes around the path and an optional trailing ``extension``.
    ``sanitize`` cleans the name (spaces kept, forbidden characters -> _).
    Exactly one of (folder, name) / error is set.
    """
    raw = (text or "").strip().strip('"').strip()
    if not raw or raw.endswith(("\\", "/")):
        return None, None, "Enter a file name."
    path = path_cls(raw)
    name = path.name
    if extension and name.lower().endswith(extension.lower()):
        name = name[: -len(extension)]
    folder = path.parent
    if str(folder) in ("", ".") or not (folder.is_absolute() or str(folder).startswith("\\\\")):
        return None, None, "Include the folder, e.g. C:\\gcode\\part."
    clean = sanitize(name).strip() if name else ""
    if not clean:
        return None, None, "Enter a file name."
    return folder, clean, None
