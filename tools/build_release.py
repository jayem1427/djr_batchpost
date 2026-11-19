#!/usr/bin/env python3
"""
Build the installable add-in zip and its release notes.

    python tools/build_release.py            # -> dist/djr_batchpost-vX.Y.Z.zip
    python tools/build_release.py --check    # only validate versions

The zip contains a single top-level folder named ``djr_batchpost`` because
Fusion requires the folder, the .py and the .manifest to share a name.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADDIN = "djr_batchpost"

# Everything Fusion needs at runtime, plus docs.
INCLUDE_FILES = [
    f"{ADDIN}.py",
    f"{ADDIN}.manifest",
    f"{ADDIN}.svg",
    "config.py",
    "README.md",
    "CHANGELOG.md",
]
INCLUDE_DIRS = ["commands", "lib", "resources/branding"]
EXCLUDE_PARTS = {"__pycache__", ".DS_Store"}
EXCLUDE_SUFFIXES = {".pyc", ".pyo", ".settings", ".xcf"}


def read_versions() -> tuple[str, str]:
    manifest = json.loads((ROOT / f"{ADDIN}.manifest").read_text(encoding="utf-8"))
    match = re.search(r"^PLUGIN_VERSION\s*=\s*['\"]([^'\"]+)['\"]",
                      (ROOT / "config.py").read_text(encoding="utf-8"), re.M)
    if not match:
        sys.exit("PLUGIN_VERSION not found in config.py")
    return manifest["version"], match.group(1)


def release_notes(version: str) -> str:
    """The version's CHANGELOG section, followed by the standard install steps
    (tools/release_install.md), so every release says how to install it."""
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    match = re.search(rf"^## v{re.escape(version)}\b.*?$(.*?)(?=^## |\Z)", text, re.M | re.S)
    if not match:
        sys.exit(f"CHANGELOG.md has no '## v{version}' section")
    install = (ROOT / "tools" / "release_install.md").read_text(encoding="utf-8")
    return match.group(1).strip() + "\n\n" + install.replace("{version}", version).strip() + "\n"


def iter_files():
    for name in INCLUDE_FILES:
        path = ROOT / name
        if not path.is_file():
            sys.exit(f"missing {name}")
        yield path
    for folder in INCLUDE_DIRS:
        for path in sorted((ROOT / folder).rglob("*")):
            if not path.is_file():
                continue
            if EXCLUDE_PARTS & set(path.parts) or path.suffix in EXCLUDE_SUFFIXES:
                continue
            yield path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="validate versions only")
    parser.add_argument("--tag", help="expected tag, e.g. v1.0.0 (CI passes the pushed tag)")
    args = parser.parse_args()

    manifest_version, config_version = read_versions()
    if manifest_version != config_version:
        sys.exit(f"version mismatch: manifest {manifest_version} vs config.py {config_version}")
    if args.tag and args.tag != f"v{manifest_version}":
        sys.exit(f"tag {args.tag} does not match version v{manifest_version}")
    notes = release_notes(manifest_version)
    if args.check:
        print(f"ok: v{manifest_version}")
        return

    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    zip_path = dist / f"{ADDIN}-v{manifest_version}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in iter_files():
            zf.write(path, f"{ADDIN}/{path.relative_to(ROOT).as_posix()}")
    (dist / "RELEASE_NOTES.md").write_text(notes, encoding="utf-8")
    print(zip_path)


if __name__ == "__main__":
    main()
