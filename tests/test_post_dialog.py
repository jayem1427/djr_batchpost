"""Post Combined dialog: parsing the File field (issue #7)."""
from pathlib import PureWindowsPath as W

from tests.conftest import install_addin_package, install_adsk_stub

install_adsk_stub()
install_addin_package()

from batch_post.commands.postProcessor.quick_post_helpers import join_target, split_target  # noqa: E402
from batch_post.lib.fusionAddInUtils.general_utils import Utils  # noqa: E402


def clean(n):
    return Utils.sanitizeFilename(n, preserveExtension=False, platformPolicy="windows")


def split(text, ext=".ngc"):
    return split_target(text, ext, clean, path_cls=W)


def test_default_round_trips():
    text = join_target(W(r"C:\gcode"), "Top side", path_cls=W)
    assert text == r"C:\gcode\Top side"
    assert split(text) == (W(r"C:\gcode"), "Top side", None)


def test_edited_name_and_folder():
    assert split(r"D:\jobs\1042\Reducer rev B") == (W(r"D:\jobs\1042"), "Reducer rev B", None)


def test_extension_typed_by_user_is_dropped():
    assert split(r"C:\gcode\part.ngc")[1] == "part"
    assert split(r"C:\gcode\part.NGC")[1] == "part"
    assert split(r"C:\gcode\part.nc")[1] == "part.nc"  # not the post's extension: kept


def test_quotes_and_spaces_trimmed():
    assert split(r'  "C:\gcode\part"  ') == (W(r"C:\gcode"), "part", None)


def test_forbidden_characters_replaced():
    assert split(r"C:\gcode\Reducer: 1?")[1] == "Reducer_ 1"


def test_errors():
    assert split("")[2] == "Enter a file name."
    assert split("   ")[2] == "Enter a file name."
    assert split("part")[2].startswith("Include the folder")
    assert split(r"gcode\part")[2].startswith("Include the folder")
    assert split("C:\\gcode\\")[2] == "Enter a file name."


def test_unc_folder_accepted():
    folder, name, error = split(r"\\shop-pc\gcode\part")
    assert error is None and name == "part"
