"""
Issue #5: restore rapids at operation entries and exits, put the motion
word in the right place, and keep the active feed correct.

All samples are inline (shaped like Fusion Personal LinuxCNC output), so
these run in CI without the gitignored .ngc captures.
"""
from __future__ import annotations

from io import StringIO
from pathlib import Path

from tests.conftest import install_addin_package, install_adsk_stub

install_adsk_stub()
install_addin_package()

from batch_post.commands.postProcessor import runtime_options  # noqa: E402
from batch_post.commands.postProcessor.gcode_helpers import (  # noqa: E402
    force_rapid_start_line,
    last_feed_word,
    rapid_end_line,
)
from batch_post.commands.postProcessor.operations.operation.body import OperationBody  # noqa: E402
from batch_post.commands.postProcessor.operations.operation.rapidsParser import RapidsParser  # noqa: E402
from batch_post.commands.postProcessor.settings import settings as settings_mod  # noqa: E402

RP = RapidsParser


def _src(tmp_path: Path, text: str, name: str = "op.ngc") -> Path:
    path = tmp_path / name
    path.write_text("\n".join(l.strip() for l in text.strip().splitlines()) + "\n", encoding="utf-8")
    return path


def _extras(path: Path) -> list[tuple[str, int, int]]:
    return [(s[RP.O_KIND], s[RP.O_START_LINE], s[RP.O_END_LINE]) for s in RP.parseEntriesAndExits(path)]


ADAPTIVE = """
G0 X10. Y20.
G43 Z50. H12
G94 G1 Z40. F3600.
Z32.905
Z31.953 F900.
X12. Y20. Z31.5 F2000.
X30. F2000.
G1 Z35. F3600.
X50. Y25.
Z31.953
Z31.5 F900.
X60. F2000.
Z50.
G53 G0 Z0.
M5
M9
M30
"""


# --- parser: entries ------------------------------------------------------------

def test_adaptive_entry_converts_two_lines_and_keeps_plunge(tmp_path):
    path = _src(tmp_path, ADAPTIVE)
    assert ("entry", 3, 4) in _extras(path)  # Z40 F3600 + Z32.905; Z31.953 F900 stays G1


def test_contour_entry_only_first_descent(tmp_path):
    path = _src(tmp_path, """
        G0 X5. Y5.
        G43 Z50. H3
        G94 G1 Z40. F1574.8
        Z36. F203.2
        X20. F500.
    """)
    assert _extras(path) == [("entry", 3, 3)]


def test_bore_entry(tmp_path):
    path = _src(tmp_path, """
        G0 X0. Y0.
        G43 Z30. H5
        G1 Z19.048 F700.
        Z18. F500.
        G3 X1. Y0. Z17. I0.5 J0.
    """)
    assert _extras(path) == [("entry", 3, 3)]


def test_single_feed_descent_after_rapid_is_left_alone(tmp_path):
    """Drilling-style: G0 to clearance then one G1 plunge into the part. No
    different F follows, so it's a real cut and must not become a rapid."""
    path = _src(tmp_path, """
        G0 X0. Y0.
        G0 Z5.
        G1 Z-10. F300.
        G0 Z5.
    """)
    assert _extras(path) == []


def test_entry_needs_preceding_rapid(tmp_path):
    path = _src(tmp_path, """
        G1 X0. Y0. F1000.
        G1 Z40. F3600.
        Z31. F900.
    """)
    assert [e for e in _extras(path) if e[0] == "entry"] == []


# --- parser: exits ----------------------------------------------------------------

def test_exit_before_g53(tmp_path):
    path = _src(tmp_path, """
        G1 X60. Z-1. F2000.
        Z50.
        G53 G0 Z0.
    """)
    assert _extras(path) == [("exit", 2, 2)]


def test_exit_skips_m_codes_and_covers_two_step_retract(tmp_path):
    path = _src(tmp_path, """
        G1 X60. Z-1. F2000.
        Z40.
        Z50.
        M9
        G0 X0. Y0.
    """)
    assert _extras(path) == [("exit", 2, 3)]


def test_exit_at_end_of_file(tmp_path):
    path = _src(tmp_path, """
        G1 X60. Z-1. F2000.
        Z50.
    """)
    assert _extras(path) == [("exit", 2, 2)]


def test_rise_followed_by_feed_xy_is_not_an_exit(tmp_path):
    path = _src(tmp_path, """
        G1 X60. Z-1. F2000.
        Z50.
        X70.
    """)
    assert _extras(path) == []


# --- force_rapid_start_line -------------------------------------------------------

def test_force_rapid_replaces_motion_word_anywhere():
    out = force_rapid_start_line(" G94 G1 Z40. F3600.\n")
    assert out == "G94 G0 Z40. (Rapid movement start)\n"
    assert "G1" not in out and "F" not in out


def test_force_rapid_leaves_other_g_codes():
    assert force_rapid_start_line("G17 G90 G01 X1.\n") == "G17 G90 G0 X1. (Rapid movement start)\n"
    assert force_rapid_start_line("G10 L2 P1 G1 X1.\n").startswith("G10 L2 P1 G0 X1.")
    assert force_rapid_start_line("G43 Z50. H12\n") == "G0 G43 Z50. H12 (Rapid movement start)\n"


def test_feed_helpers():
    assert last_feed_word("G94 G1 Z40. F3600. (note F9)") == "3600."
    assert last_feed_word("Z32.905") is None
    assert rapid_end_line("3600.") == "G1 F3600. (Rapid movement end)\n"
    assert rapid_end_line(None) == "G1 (Rapid movement end)\n"


# --- WriteBody end to end ---------------------------------------------------------------

class _Body(OperationBody):
    def __init__(self, path: Path, tail_start: int):
        self._tempFilePath = path
        self._bodyStartLine = 0
        self._tailStartLine = tail_start
        self._rotationLine = -1
        self._allowBlankLines = False
        self._lineNumber = 0
        self._rapidsAnalysis = {}
        self.name = "Adaptive"


def _write(path: Path, tail_start: int, min_dist: float = 20) -> list[str]:
    base = dict(settings_mod.Settings._defaultSettings)
    base[settings_mod.Settings.LINE_SEQUENCE] = False
    settings_mod.Settings._default = dict(base)
    settings_mod.Settings._items = dict(base)
    runtime_options.restore_rapid_moves = True
    runtime_options.rapid_moves_minimum_distance = min_dist
    try:
        out = StringIO()
        _Body(path, tail_start).WriteBody(out)
        return out.getvalue().splitlines()
    finally:
        runtime_options.restore_rapid_moves = False


def test_writebody_restores_entry_link_and_exit(tmp_path):
    lines = _write(_src(tmp_path, ADAPTIVE), tail_start=14)  # M5 is line index 14
    text = "\n".join(lines)
    assert "(Rapid restore: 3 segment[s])" in text

    # Entry: two rapids, feed restored to the stand-in value, real plunge untouched.
    i = lines.index("G94 G0 Z40. (Rapid movement start)")
    assert lines[i + 1] == "Z32.905"
    assert lines[i + 2] == "G1 F3600. (Rapid movement end)"
    assert lines[i + 3] == "Z31.953 F900."

    # Link still restored, and its end marker restores F.
    j = lines.index("G0 Z35. (Rapid movement start)")
    assert lines[j + 1: j + 4] == ["X50. Y25.", "Z31.953", "G1 F3600. (Rapid movement end)"]

    # Exit: retract is a rapid, then back to feed before G53.
    k = lines.index("G0 Z50. (Rapid movement start)")
    assert lines[k + 1] == "G1 (Rapid movement end)"
    assert lines[k + 2] == "G53 G0 Z0."

    # Done-when from the issue: no G1 left at clearance/retract heights.
    for line in lines:
        if "Rapid movement" in line:
            continue
        assert line not in ("G94 G1 Z40. F3600.", "Z50.", "G1 Z35. F3600.")


def test_link_followed_by_cutting_line_without_f_keeps_feed(tmp_path):
    """Latent bug #4: the cutting line after a restored link has no F. Before
    the fix the stripped F3600 was lost and it ran at an older feed."""
    path = _src(tmp_path, """
        G1 X0. Y0. Z-1. F500.
        G1 Z5. F3600.
        X40. Y0.
        Z-0.5
        X60.
        M30
    """)
    lines = _write(path, tail_start=5, min_dist=5)
    i = lines.index("G0 Z5. (Rapid movement start)")
    assert lines[i + 1: i + 4] == ["X40. Y0.", "Z-0.5", "G1 F3600. (Rapid movement end)"]
    assert lines[i + 4] == "X60."


def test_restore_off_changes_nothing(tmp_path):
    path = _src(tmp_path, ADAPTIVE)
    out = StringIO()
    runtime_options.restore_rapid_moves = False
    _Body(path, 14).WriteBody(out)
    assert "Rapid movement" not in out.getvalue()
    assert "G94 G1 Z40. F3600." in out.getvalue()
