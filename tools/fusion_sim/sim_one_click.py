"""One-click posting: auto NC Program + right-click on a setup."""
import importlib
import json
import shutil
import sys
import tempfile
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import fake_fusion

posts = []
F = fake_fusion.install(posts)
core = F.core
ADDIN_DIR = Path(sys.argv[1]).resolve()
pkg = types.ModuleType("djr_batchpost")
pkg.__path__ = [str(ADDIN_DIR)]
pkg.__file__ = str(ADDIN_DIR / "__init__.py")
sys.modules["djr_batchpost"] = pkg
entry = importlib.import_module("djr_batchpost.djr_batchpost")
from djr_batchpost.commands.postProcessor import config, post_memory

app = F.Application.get()
ui = app.userInterface
entry.run(None)
Yes, No = core.DialogResults.DialogYes, core.DialogResults.DialogNo

tmp = Path(tempfile.mkdtemp())
out = tmp / "gcode"
out.mkdir()
F.DEFAULT_OUT[0] = out
LIB = F.POST_LIBRARY
mypost = types.SimpleNamespace(description="LemonTart LinuxCNC", vendor="LinuxCNC", extension=".ngc", capability=1)
remember_file = post_memory.path()
if remember_file.exists():
    remember_file.unlink()


def make_doc(programs=()):
    t1, t2 = F.Tool(1, "6mm flat"), F.Tool(2, "drill")
    s1 = F.Setup("Top side", [F.Op("Face", t1), F.Op("Pocket", t1)])
    s2 = F.Setup("Bottom side", [F.Op("Drill", t2)])
    camp = F.CAMProduct(list(programs), [s1, s2])
    return F.Document(camp, "Test Bracket v7"), camp, s1, s2


def press(cmd_id, answers):
    ui.messages.clear()
    ui.answers = list(answers)
    ui.commandDefinitions.itemById(cmd_id).execute()
    return [(t, m.split("<")[0][:100]) for t, m, _ in ui.messages]


# A. no NC Program, nothing remembered, two posts in the user's library -> asks, creates nothing
LIB.tree = {"loc0://": {"posts": [mypost, types.SimpleNamespace(description="Other", vendor="X", extension=".nc")]}}
doc, camp, s1, s2 = make_doc()
app.activeDocument = doc
msgs = press(config.QUICK_CMD_ID, [])
print("A:", msgs)
assert "don't know your post processor yet" in msgs[0][1] and len(camp.ncPrograms) == 0

# B. exactly one post in the user's library (in a subfolder) -> NC Program created, combined file named after the doc
LIB.tree = {"loc0://": {"folders": ["loc0://shop"]}, "loc0://shop": {"posts": [mypost]}}
msgs = press(config.QUICK_CMD_ID, [No])
print("B:", msgs)
assert len(camp.ncPrograms) == 1
prog = camp.ncPrograms[0]
assert prog.name == "DJR Batch Post" and prog.postConfiguration is mypost
assert len(prog.operations) == 2
assert (out / "Test Bracket.ngc").is_file(), list(out.iterdir())
assert "Wrote 1 file(s)" in msgs[-1][1]
remembered = json.loads(remember_file.read_text())
print("   remembered:", remembered)
assert remembered["description"] == "LemonTart LinuxCNC" and remembered["outputFolder"] == str(out)

# C. new document, remembered post now found among many (Fusion library) -> created automatically
LIB.tree = {"loc0://": {"posts": [types.SimpleNamespace(description="A", vendor="A", extension=".nc"),
                                  types.SimpleNamespace(description="B", vendor="B", extension=".nc")]},
            "loc5://": {"posts": [mypost]}}
shutil.rmtree(out); out.mkdir()
F.DEFAULT_OUT[0] = tmp / "somewhere-else"  # Fusion default differs; remembered folder must win
doc, camp, s1, s2 = make_doc()
app.activeDocument = doc
msgs = press(config.QUICK_CMD_ID, [No])
print("C:", msgs)
assert camp.ncPrograms[0].postConfiguration is mypost
assert (out / "Test Bracket.ngc").is_file(), "remembered output folder not used"

# D. right-click 'Bottom side' -> menu entry appears; run -> only that setup, file named after it
ids = ui.right_click([s2])
print("D menu:", ids)
assert config.QUICK_CTX_CMD_ID in ids
assert ui.right_click([types.SimpleNamespace(objectType="adsk::fusion::BRepBody")]) == [], "menu entry on non-setup"
ui.right_click([s2])
n = len(posts)
msgs = press(config.QUICK_CTX_CMD_ID, [No])
print("D:", msgs, posts[n:])
assert posts[n:] == [["Drill"]], posts[n:]
t = (out / "Bottom side.ngc").read_text()
assert "(Drill)" in t and "(Face)" not in t
assert camp.ncPrograms[0].parameters.itemByName("nc_program_filename").value.value == "Test Bracket", "file name not restored"

# E. right-click both setups -> one combined file with the program's name
ui.right_click([s1, s2])
(out / "Test Bracket.ngc").unlink()
msgs = press(config.QUICK_CTX_CMD_ID, [No])
t = (out / "Test Bracket.ngc").read_text()
assert "(Face)" in t and "(Drill)" in t
print("E: both setups -> Test Bracket.ngc ok")

# F. existing NC Program with a post is used as-is (no new program)
doc, camp, s1, s2 = make_doc([F.NCProgram("Mine", out, "9000")])
app.activeDocument = doc
press(config.QUICK_CMD_ID, [No])
assert len(camp.ncPrograms) == 1 and (out / "9000.ngc").is_file()
print("F: existing program used")

# G. stop removes buttons, definitions and the right-click hook
entry.stop(None)
assert not ui.commandDefinitions._items and ui.markingMenuDisplaying.handlers == []
assert [c.id for c in ui.panel._controls] == ["IronPostProcess"]
remember_file.unlink()
print("\nALL ONE-CLICK CHECKS PASSED")
