"""
One-click posting without an NC Program: remembering the post, finding it
again in the post libraries, and naming files.
"""
from __future__ import annotations

import types
from pathlib import Path

from tests.conftest import install_addin_package, install_adsk_stub

install_adsk_stub()
install_addin_package()

from batch_post.commands.postProcessor import post_memory as pm  # noqa: E402
from batch_post.commands.postProcessor.quick_post_helpers import program_file_name  # noqa: E402


def _post(desc, vendor="LinuxCNC", ext=".ngc"):
    return types.SimpleNamespace(description=desc, vendor=vendor, extension=ext)


class _Library:
    """Folders as nested dicts: {'posts': [...], 'folders': {url: {...}}}."""

    def __init__(self, tree):
        self._nodes = {}

        def walk(url, node):
            self._nodes[url] = node
            for sub_url, sub in node.get("folders", {}).items():
                walk(sub_url, sub)
        for url, node in tree.items():
            walk(url, node)

    def childPostConfigurations(self, url):
        return self._nodes.get(url, {}).get("posts", [])

    def childFolderURLs(self, url):
        return list(self._nodes.get(url, {}).get("folders", {}).keys())


def test_remember_roundtrip(tmp_path: Path):
    f = tmp_path / "remembered_post.json"
    info = pm.describe_post(_post("LemonTart LinuxCNC"), r"C:\gcode")
    pm.save(info, f)
    assert pm.load(f) == {"description": "LemonTart LinuxCNC", "vendor": "LinuxCNC",
                          "extension": ".ngc", "outputFolder": r"C:\gcode"}
    assert pm.load(tmp_path / "missing.json") == {}
    (tmp_path / "bad.json").write_text("{not json")
    assert pm.load(tmp_path / "bad.json") == {}


def test_match_needs_same_description_vendor_extension():
    info = {"description": "LinuxCNC", "vendor": "LinuxCNC", "extension": ".ngc"}
    assert pm.matches(_post("LinuxCNC"), info)
    assert not pm.matches(_post("LinuxCNC", ext=".nc"), info)
    assert not pm.matches(_post("LinuxCNC", vendor="Haas"), info)
    assert not pm.matches(_post("Other"), info)
    assert not pm.matches(_post("LinuxCNC"), {})


def test_find_post_searches_subfolders_and_prefers_first_location():
    mine = _post("LinuxCNC")
    builtin = _post("LinuxCNC")
    lib = _Library({
        "local://": {"posts": [_post("Fanuc", "Fanuc", ".nc")],
                     "folders": {"local://shop": {"folders": {"local://shop/mill": {"posts": [mine]}}}}},
        "fusion://": {"posts": [builtin]},
    })
    found = pm.find_post(lib, ["local://", "fusion://"], pm.describe_post(mine))
    assert found is mine
    assert pm.find_post(lib, ["local://"], {"description": "Nope"}) is None


def test_only_post_when_exactly_one():
    one = _post("Mine")
    assert pm.only_post(_Library({"a": {"posts": [one]}, "b": {}}), ["a", "b"]) is one
    assert pm.only_post(_Library({"a": {"posts": [one, _post("x")]}}), ["a"]) is None
    assert pm.only_post(_Library({"a": {}}), ["a"]) is None


def test_library_errors_are_skipped():
    class Broken:
        def childPostConfigurations(self, url):
            raise RuntimeError("offline")

        def childFolderURLs(self, url):
            raise RuntimeError("offline")
    assert pm.find_post(Broken(), ["cloud://"], {"description": "x"}) is None


def test_program_file_name_strips_fusion_version():
    assert program_file_name("Bracket v12") == "Bracket"
    assert program_file_name("Grid Vacuum Plate 120x120 v3") == "Grid Vacuum Plate 120x120"
    assert program_file_name("v2 adapter") == "v2 adapter"
    assert program_file_name("") == "program"
