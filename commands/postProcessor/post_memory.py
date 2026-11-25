"""
Remembers the post processor (and output folder) of the last successful
post, so a document without an NC Program can get one automatically.

PostConfiguration objects have no URL, so a post is remembered by its
description + vendor + extension and found again by searching the post
libraries. Nothing in here imports ``adsk``; library objects are passed in.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Optional

_FILE = Path(__file__).parent / "settings" / "remembered_post.json"
_MAX_DEPTH = 4
_MAX_FOLDERS = 400


def path() -> Path:
    return _FILE


def load(file: Optional[Path] = None) -> dict:
    file = file or _FILE
    try:
        data = json.loads(Path(file).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) and data.get("description") else {}
    except Exception:
        return {}


def save(info: dict, file: Optional[Path] = None) -> None:
    file = file or _FILE
    try:
        Path(file).write_text(json.dumps(info, indent=2), encoding="utf-8")
    except Exception:
        pass


def describe_post(post_configuration, output_folder: Optional[str] = None) -> dict:
    info = {
        "description": getattr(post_configuration, "description", "") or "",
        "vendor": getattr(post_configuration, "vendor", "") or "",
        "extension": getattr(post_configuration, "extension", "") or "",
    }
    if output_folder:
        info["outputFolder"] = str(output_folder)
    return info


def matches(post_configuration, info: dict) -> bool:
    if not info or not info.get("description"):
        return False
    if (getattr(post_configuration, "description", "") or "") != info["description"]:
        return False
    for key in ("vendor", "extension"):
        wanted = info.get(key)
        if wanted and (getattr(post_configuration, key, "") or "") != wanted:
            return False
    return True


def iter_posts(library, root_urls: Iterable) -> Iterable:
    """Yield posts from each library in turn (so your own libraries win over
    Fusion's), walking each one's folders breadth-first, bounded."""
    for root in root_urls:
        if root is not None:
            yield from _iter_tree(library, root)


def _iter_tree(library, root) -> Iterable:
    queue = [(root, 0)]
    visited = 0
    while queue and visited < _MAX_FOLDERS:
        url, depth = queue.pop(0)
        visited += 1
        try:
            posts = library.childPostConfigurations(url) or []
        except Exception:
            posts = []
        for post in posts:
            yield post
        if depth >= _MAX_DEPTH:
            continue
        try:
            folders = library.childFolderURLs(url) or []
        except Exception:
            folders = []
        queue.extend((folder, depth + 1) for folder in folders)


def find_post(library, root_urls: Iterable, info: dict):
    """The remembered post, searching ``root_urls`` in order (None if absent)."""
    for post in iter_posts(library, root_urls):
        if matches(post, info):
            return post
    return None


def only_post(library, root_urls: Iterable):
    """If the user's own libraries hold exactly one post, return it."""
    found = []
    for post in iter_posts(library, root_urls):
        found.append(post)
        if len(found) > 1:
            return None
    return found[0] if found else None


def list_posts(library, root_urls: Iterable, limit: int = 300) -> list:
    """Posts found in ``root_urls`` (in order), without duplicates, capped."""
    seen = set()
    out = []
    for post in iter_posts(library, root_urls):
        key = (getattr(post, "description", ""), getattr(post, "vendor", ""), getattr(post, "extension", ""))
        if key in seen:
            continue
        seen.add(key)
        out.append(post)
        if len(out) >= limit:
            break
    return out


def post_label(post) -> str:
    description = getattr(post, "description", "") or "(unnamed post)"
    vendor = getattr(post, "vendor", "") or ""
    extension = getattr(post, "extension", "") or ""
    extra = ", ".join(x for x in (vendor, extension) if x)
    return f"{description} ({extra})" if extra else description
