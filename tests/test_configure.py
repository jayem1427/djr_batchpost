"""Configure DJR Batch Post: saving the post, output folder and defaults."""
from __future__ import annotations

import json
import types

import pytest

from tests.conftest import install_addin_package, install_adsk_stub

install_adsk_stub()
install_addin_package()

from batch_post.commands.postProcessor import configure, post_memory  # noqa: E402
from batch_post.commands.postProcessor.settings.settings import Settings  # noqa: E402


@pytest.fixture
def files(tmp_path, monkeypatch):
    post_file = tmp_path / "remembered_post.json"
    defaults_file = tmp_path / "settings.settings"
    monkeypatch.setattr(post_memory, "_FILE", post_file)
    monkeypatch.setattr(Settings, "_path", str(defaults_file))
    monkeypatch.setattr(Settings, "_default", None)
    monkeypatch.setattr(Settings, "_items", dict(Settings._defaultSettings))
    return post_file, defaults_file


def _post(desc="LemonTart LinuxCNC"):
    return types.SimpleNamespace(description=desc, vendor="LinuxCNC", extension=".ngc")


class _Program:
    name = "NCProgram1"

    def __init__(self):
        self._program = types.SimpleNamespace(postConfiguration=None)
        self.folder = None

    def SetOutputFolder(self, folder):
        folder.as_posix()  # the real wrapper needs a Path
        self.folder = folder


def test_saves_post_and_folder(files):
    post_file, _ = files
    changed = configure.apply_configuration(_post(), r"C:\gcode", None, {})
    saved = json.loads(post_file.read_text())
    assert saved["description"] == "LemonTart LinuxCNC" and saved["outputFolder"] == r"C:\gcode"
    assert any("LemonTart LinuxCNC" in c for c in changed)


def test_folder_only_keeps_remembered_post(files):
    post_file, _ = files
    post_memory.save(post_memory.describe_post(_post(), r"C:\old"))
    configure.apply_configuration(None, r"D:\new", None, {})
    saved = json.loads(post_file.read_text())
    assert saved["description"] == "LemonTart LinuxCNC" and saved["outputFolder"] == r"D:\new"


def test_keep_current_changes_nothing(files):
    post_file, defaults_file = files
    assert configure.apply_configuration(None, "", None, {}) == []
    assert not post_file.exists() and not defaults_file.exists()


def test_defaults_written_without_touching_open_document(files):
    _, defaults_file = files
    Settings._items[Settings.RESTORE_RAPID_MOVES] = False  # open document's own value
    configure.apply_configuration(None, "", None, {Settings.RESTORE_RAPID_MOVES: True,
                                                   Settings.RAPID_MOVES_MINIMUM_DISTANCE: 25.0})
    written = json.loads(defaults_file.read_text())
    assert written[Settings.RESTORE_RAPID_MOVES] is True
    assert written[Settings.RAPID_MOVES_MINIMUM_DISTANCE] == 25.0
    assert written[Settings.END_CODES] == Settings._defaultSettings[Settings.END_CODES]  # other keys kept
    assert Settings._items[Settings.RESTORE_RAPID_MOVES] is False


def test_applies_to_document_program(files):
    program = _Program()
    post = _post()
    configure.apply_configuration(post, r"C:\gcode", program, {})
    assert program._program.postConfiguration is post
    assert str(program.folder) == r"C:\gcode"


def test_post_label():
    assert post_memory.post_label(_post()) == "LemonTart LinuxCNC (LinuxCNC, .ngc)"
    assert post_memory.post_label(types.SimpleNamespace(description="", vendor="", extension="")) == "(unnamed post)"
