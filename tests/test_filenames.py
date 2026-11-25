"""Output file names keep their spaces; unsafe characters are still replaced."""
from tests.conftest import install_addin_package, install_adsk_stub

install_adsk_stub()
install_addin_package()

from batch_post.lib.fusionAddInUtils.general_utils import Utils  # noqa: E402


def name(s, **kw):
    return Utils.sanitizeFilename(s, preserveExtension=False, platformPolicy="windows", **kw)


def test_spaces_are_kept():
    assert name("Top side") == "Top side"
    assert name("Grid Vacuum Plate 120x120") == "Grid Vacuum Plate 120x120"


def test_whitespace_runs_and_edges_cleaned():
    assert name("  Op1  -\tBottom  ") == "Op1 - Bottom"


def test_unsafe_characters_still_replaced():
    assert name('Reducer: 1/2" bore?') == "Reducer_ 1_2_ bore"
    assert name("CON") == "CON_"
