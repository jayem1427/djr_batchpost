"""
Tests for the faster combined-post workflow: NC Program preselection,
single-file defaults, overwrite prompting, and the written-files report.
"""
from __future__ import annotations

import types
from pathlib import Path

import pytest

from tests.conftest import install_addin_package, install_adsk_stub

install_adsk_stub()
install_addin_package()

from batch_post.commands.postProcessor import quick_post_helpers as qph  # noqa: E402
from batch_post.commands.postProcessor import run_report  # noqa: E402
from batch_post.commands.postProcessor.settings import settings as settings_mod  # noqa: E402

Settings = settings_mod.Settings


def _program(name, *, error=False, empty=False, suppressed=False, post=True):
    return types.SimpleNamespace(name=name, hasError=error, isEmpty=empty,
                                 isSuppressed=suppressed, hasPostProcessor=post)


def _reset_settings(**overrides):
    base = dict(Settings._defaultSettings)
    base.update(overrides)
    Settings._default = dict(base)
    Settings._items = dict(base)


# --- NC Program preselection -------------------------------------------------

def test_saved_program_wins_when_usable():
    progs = [_program("A"), _program("B")]
    assert qph.pick_default_program(progs, "B").name == "B"


def test_saved_program_ignored_when_unusable():
    progs = [_program("A"), _program("B", error=True)]
    assert qph.pick_default_program(progs, "B").name == "A"


def test_prefers_program_with_post_processor():
    progs = [_program("NoPost", post=False), _program("WithPost")]
    assert qph.pick_default_program(progs, "").name == "WithPost"


def test_falls_back_to_first_usable_without_post():
    progs = [_program("Empty", empty=True), _program("NoPost", post=False)]
    assert qph.pick_default_program(progs, None).name == "NoPost"


def test_no_usable_program_returns_none():
    progs = [_program("X", suppressed=True), _program("Y", empty=True)]
    assert qph.pick_default_program(progs, "X") is None


# --- Defaults ----------------------------------------------------------------

def test_new_documents_default_to_single_combined_file():
    assert Settings._defaultSettings[Settings.OPERATIONS_GROUPING] == Settings.OperationsGroupings.SINGLE_FILE


def test_settings_attribute_group_survives_rename():
    # Per-document settings are stored under this key; renaming it would
    # silently reset every existing document's settings.
    from batch_post.commands.postProcessor.const import Const
    assert Const.ATTR_GROUP == "BatchPost_Post_Processor"


# --- Output paths and report ---------------------------------------------------

def test_combined_output_path_matches_writer(tmp_path: Path):
    assert qph.combined_output_path(tmp_path, "1001", ".ngc") == tmp_path / "1001.ngc"
    assert qph.combined_output_path(str(tmp_path), "part", None) == tmp_path / "part"


def test_first_header_records_written_file(tmp_path: Path):
    """WriteFirstHeaderStart must report the exact file the precheck targets."""
    from batch_post.commands.postProcessor.operations.header import OperationsHeader

    _reset_settings(**{Settings.OVERWRITE_FILES: False})

    class _Op:
        lineNumber = 3

        def WriteHeaderStart(self, fh):
            fh.write("%\n")

    holder = OperationsHeader()
    holder._operations = [_Op()]
    holder._path = tmp_path
    holder._fileName = "1001"
    holder._fileExtension = ".ngc"
    holder._lineNumber = 0

    run_report.reset()
    holder.WriteFirstHeaderStart()
    expected = qph.combined_output_path(tmp_path, "1001", ".ngc")
    assert run_report.written() == [expected]
    assert expected.read_text() == "%\n"

    # Second run without overwrite must refuse instead of clobbering.
    with pytest.raises(FileExistsError):
        holder.WriteFirstHeaderStart()


def test_report_dedupes_and_keeps_order(tmp_path: Path):
    run_report.reset()
    run_report.record(tmp_path / "b.ngc")
    run_report.record(tmp_path / "a.ngc")
    run_report.record(tmp_path / "b.ngc")
    assert run_report.written() == [tmp_path / "b.ngc", tmp_path / "a.ngc"]


def test_common_folder_and_description(tmp_path: Path):
    files = [tmp_path / "Setup1" / "T1.ngc", tmp_path / "Setup2" / "T2.ngc"]
    assert qph.common_folder(files) == tmp_path
    assert qph.common_folder([]) is None
    many = [tmp_path / f"{i}.ngc" for i in range(10)]
    text = qph.describe_outputs(many, limit=3)
    assert text.startswith("0.ngc<br>1.ngc<br>2.ngc")
    assert "7 more" in text


# --- Overwrite prompt ----------------------------------------------------------

@pytest.fixture
def runner(monkeypatch, tmp_path):
    from batch_post.commands.postProcessor import post_runner

    program = types.SimpleNamespace(
        GetOutputFolder=lambda: tmp_path, fileName="1001", fileExtension=".ngc")
    monkeypatch.setattr(post_runner.Programs, "_current", program)
    calls = {"runs": 0, "asked": [], "overwrite_during_run": []}

    def fake_run():
        calls["runs"] += 1
        calls["overwrite_during_run"].append(Settings(Settings.OVERWRITE_FILES))
        return [tmp_path / "1001.ngc"]

    monkeypatch.setattr(post_runner, "run_post", fake_run)
    return post_runner, calls, tmp_path


def _answer(post_runner, monkeypatch, calls, yes: bool):
    def ask(ui, detail):
        calls["asked"].append(detail)
        return yes
    monkeypatch.setattr(post_runner, "ask_overwrite", ask)


def test_no_prompt_when_target_is_new(runner, monkeypatch):
    post_runner, calls, _ = runner
    _reset_settings(**{Settings.OPERATIONS_GROUPING: Settings.OperationsGroupings.SINGLE_FILE})
    _answer(post_runner, monkeypatch, calls, True)
    assert post_runner.run_with_overwrite_prompt(None)
    assert calls["asked"] == [] and calls["runs"] == 1


def test_existing_target_asks_before_posting(runner, monkeypatch):
    post_runner, calls, tmp = runner
    (tmp / "1001.ngc").write_text("old")
    _reset_settings(**{Settings.OPERATIONS_GROUPING: Settings.OperationsGroupings.SINGLE_FILE})
    _answer(post_runner, monkeypatch, calls, False)
    assert post_runner.run_with_overwrite_prompt(None) is None
    assert calls["runs"] == 0  # nothing posted after "No"
    assert len(calls["asked"]) == 1


def test_yes_overwrites_for_this_run_only(runner, monkeypatch):
    post_runner, calls, tmp = runner
    (tmp / "1001.ngc").write_text("old")
    _reset_settings(**{Settings.OPERATIONS_GROUPING: Settings.OperationsGroupings.SINGLE_FILE,
                       Settings.OVERWRITE_FILES: False})
    _answer(post_runner, monkeypatch, calls, True)
    assert post_runner.run_with_overwrite_prompt(None) == [tmp / "1001.ngc"]
    assert calls["overwrite_during_run"] == [True]
    assert Settings(Settings.OVERWRITE_FILES) is False  # restored


def test_multi_file_clash_retries_once_after_yes(runner, monkeypatch):
    post_runner, calls, tmp = runner
    _reset_settings(**{Settings.OPERATIONS_GROUPING: Settings.OperationsGroupings.SETUP,
                       Settings.OVERWRITE_FILES: False})
    state = {"first": True}

    def flaky_run():
        calls["overwrite_during_run"].append(Settings(Settings.OVERWRITE_FILES))
        if state["first"]:
            state["first"] = False
            raise FileExistsError("File Setup1.ngc already exists and overwrite is not allowed.")
        return [tmp / "Setup1.ngc"]

    monkeypatch.setattr(post_runner, "run_post", flaky_run)
    _answer(post_runner, monkeypatch, calls, True)
    assert post_runner.run_with_overwrite_prompt(None) == [tmp / "Setup1.ngc"]
    assert calls["overwrite_during_run"] == [False, True]
    assert Settings(Settings.OVERWRITE_FILES) is False


def test_overwrite_already_on_never_prompts(runner, monkeypatch):
    post_runner, calls, tmp = runner
    (tmp / "1001.ngc").write_text("old")
    _reset_settings(**{Settings.OPERATIONS_GROUPING: Settings.OperationsGroupings.SINGLE_FILE,
                       Settings.OVERWRITE_FILES: True})
    _answer(post_runner, monkeypatch, calls, False)
    assert post_runner.run_with_overwrite_prompt(None)
    assert calls["asked"] == []


# --- Wiring ----------------------------------------------------------------

def test_commands_register_dialog_then_quick_post():
    from batch_post.commands.commands import Commands
    from batch_post.commands.postProcessor.dialog.dialog import PostDialog
    from batch_post.commands.postProcessor.quick_post import QuickPostCommand
    from batch_post.commands.postProcessor.configure import ConfigureCommand
    assert Commands._commands == [PostDialog, QuickPostCommand, ConfigureCommand]


def test_icon_folders_have_fusion_icon_sizes():
    from batch_post.commands.postProcessor.dialog.dialog import PostDialog
    from batch_post.commands.postProcessor.quick_post import QuickPostCommand
    from batch_post.commands.postProcessor.configure import ConfigureCommand
    for folder in (PostDialog._ICON_FOLDER, QuickPostCommand._ICON_FOLDER, ConfigureCommand._ICON_FOLDER):
        for name in ("16x16.png", "32x32.png", "64x64.png", "16x16@2x.png", "32x32@2x.png"):
            assert (Path(folder) / name).is_file(), f"{folder}{name}"


def test_manifest_and_config_versions_match():
    import json
    from batch_post.config import PLUGIN_VERSION
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / "djr_batchpost.manifest").read_text())
    assert manifest["version"] == PLUGIN_VERSION
    assert (root / manifest["iconFilename"]).is_file()
    assert (root / "djr_batchpost.py").is_file()


def test_changing_a_setting_does_not_overwrite_saved_defaults(tmp_path, monkeypatch):
    """Defaults for new documents change only via 'Save as default settings'."""
    defaults_file = tmp_path / "settings.settings"
    monkeypatch.setattr(Settings, "_path", str(defaults_file))
    _reset_settings()
    Settings._fMustSave = False
    Settings.Set(Settings.OVERWRITE_FILES, True)

    class _Attrs:
        def __init__(self):
            self.saved = {}

        def add(self, g, n, v):
            self.saved[(g, n)] = v

    attrs = _Attrs()
    Settings.Save(attrs)
    assert attrs.saved, "document settings must still be saved"
    assert not defaults_file.exists(), "Set() must not rewrite the defaults file"

    Settings.SaveDefault()
    assert defaults_file.exists()


def test_new_document_starts_from_defaults_not_previous_document(tmp_path, monkeypatch):
    import json as _json
    from batch_post.commands.postProcessor.const import Const
    monkeypatch.setattr(Settings, "_path", str(tmp_path / "none.settings"))
    monkeypatch.setattr(Settings, "_default", None)

    class _Attrs:
        def __init__(self, items=None):
            self._v = {} if items is None else {(Const.ATTR_GROUP, Const.ATTR_NAME): types.SimpleNamespace(value=_json.dumps(items))}

        @property
        def count(self):
            return len(self._v)

        def itemByName(self, g, n):
            return self._v.get((g, n))

    first = dict(Settings._defaultSettings)
    first[Settings.OVERWRITE_FILES] = True
    first[Settings.OPERATIONS_GROUPING] = Settings.OperationsGroupings.PER_OPERATION
    Settings.Load(_Attrs(first))
    assert Settings(Settings.OVERWRITE_FILES) is True

    Settings.Load(_Attrs())  # a different document with no saved settings
    assert Settings(Settings.OVERWRITE_FILES) is False
    assert Settings(Settings.OPERATIONS_GROUPING) == Settings.OperationsGroupings.SINGLE_FILE

    old = {Settings.VERSION: 1, Settings.COMBINE_TOOL: True}
    Settings.Load(_Attrs(old))  # older settings version keeps its values
    assert Settings(Settings.COMBINE_TOOL) is True
    assert Settings(Settings.END_CODES) == "M5\nM9\nM30"
