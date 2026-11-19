"""Every release's notes must include the install steps."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("build_release", ROOT / "tools" / "build_release.py")
build_release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build_release)


def test_release_notes_have_changelog_and_install_steps():
    version, _ = build_release.read_versions()
    notes = build_release.release_notes(version)
    assert "## Install / upgrade" in notes
    assert f"djr_batchpost-v{version}.zip" in notes
    assert "{version}" not in notes
    assert r"%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns" in notes
    # Changelog part comes first, install steps last.
    assert notes.index("## Install / upgrade") > len(notes) // 3
