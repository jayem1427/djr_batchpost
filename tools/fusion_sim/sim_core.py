"""Core posting flow: buttons, combined file, overwrite prompt, dialog Process, browser selection."""
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

# Fusion imports the add-in folder as a package and the same-named .py inside it.
pkg = types.ModuleType("djr_batchpost")
pkg.__path__ = [str(ADDIN_DIR)]
pkg.__file__ = str(ADDIN_DIR / "__init__.py")
sys.modules["djr_batchpost"] = pkg
entry = importlib.import_module("djr_batchpost.djr_batchpost")

app = F.Application.get()
ui = app.userInterface
entry.run(None)

ids = [c.id for c in ui.panel._controls]
print("controls:", ids)
from djr_batchpost.commands.postProcessor import config
assert ids == ["IronPostProcess", config.CMD_ID, config.QUICK_CMD_ID], ids
for d in ui.commandDefinitions._items.values():
    assert Path(d.resourceFolder, "16x16.png").is_file(), d.resourceFolder
    print("definition:", d.id, "|", d.name, "|", Path(d.resourceFolder).name)
assert all(c.isPromoted for c in ui.panel._controls[1:])

tmp = Path(tempfile.mkdtemp())
out = tmp / "out"
out.mkdir()
Rx90 = F.Matrix([[1, 0, 0], [0, 0, -1], [0, 1, 0]])


def make_doc(rotated=False):
    t1, t2, t3 = F.Tool(1, "6mm flat"), F.Tool(2, "3mm ball"), F.Tool(3, "drill")
    s1 = F.Setup("Setup1", [F.Op("Face", t1), F.Op("Pocket", t1), F.Op("Contour", t2)])
    s2 = F.Setup("Setup2", [F.Op("Drill", t3)], wcs=Rx90 if rotated else F.Matrix([[1, 0, 0], [0, 1, 0], [0, 0, 1]]))
    prog = F.NCProgram("NCProgram1", out, "1001")
    return F.Document(F.CAMProduct([prog], [s1, s2])), prog


def click(cmd_id, answers):
    ui.messages.clear()
    ui.answers = list(answers)
    ui.commandDefinitions.itemById(cmd_id).execute()
    left = ui.answers
    return [(t, txt.split("<")[0][:90]) for t, txt, _ in ui.messages], left


Yes, No, OK = core.DialogResults.DialogYes, core.DialogResults.DialogNo, core.DialogResults.DialogOK

# --- 1. first click on a fresh document ------------------------------------
doc, prog = make_doc()
app.activeDocument = doc
msgs, left = click(config.QUICK_CMD_ID, [No])
print("1 messages:", msgs)
target = out / "1001.ngc"
assert target.is_file(), "combined file not written"
assert msgs and msgs[-1][1].startswith("Wrote 1 file(s)"), msgs
text = target.read_text()
pass
assert text.count("M30") == 1 and text.rstrip().endswith("M30") and "%" not in text
for op in ("Face", "Pocket", "Contour", "Drill"):
    assert f"({op})" in text, op
assert text.count("G21") == 1, "header duplicated"
from djr_batchpost.config import PLUGIN_VERSION
assert f"Generated with DJR Batch Post version {PLUGIN_VERSION}" in text
assert text.index("(Contour)") < text.index("(Drill)")
assert prog.parameters.itemByName("nc_program_filename").value.value == "1001"
assert prog.parameters.itemByName("nc_program_output_folder").value.value == str(out)
posts_after_first = len(posts)
print("posts:", posts)

# --- 2. re-click: file exists, answer No -> nothing is posted -----------------
msgs, _ = click(config.QUICK_CMD_ID, [No])
print("2 messages:", msgs)
assert "already exists" in msgs[0][1] and len(msgs) == 1
assert len(posts) == posts_after_first, "posted even though user declined overwrite"

# --- 3. re-click: Yes overwrite, No open folder -----------------------------
target.write_text("stale")
msgs, _ = click(config.QUICK_CMD_ID, [Yes, No])
print("3 messages:", msgs)
assert target.read_text() != "stale" and "M30" in target.read_text()
saved = json.loads(doc.attributes.itemByName("BatchPost_Post_Processor", "settings").value)
assert saved["overwriteFiles"] is False, "overwrite leaked into saved settings"
assert saved["ncProgram"] == "NCProgram1"

# --- 4. document saved with 'Group on setup' + clear folder: quick still makes one file
saved.update({"operationsGrouping": 1, "clearFolder": True, "overwriteFiles": True})
doc.attributes.add("BatchPost_Post_Processor", "settings", json.dumps(saved))
(out / "keep_me.txt").write_text("user file")
target.unlink()
msgs, _ = click(config.QUICK_CMD_ID, [No])
print("4 messages:", msgs)
assert target.is_file() and (out / "keep_me.txt").is_file(), "folder was cleared or file missing"
assert not (out / "1001").exists(), "per-setup subfolder created"
saved2 = json.loads(doc.attributes.itemByName("BatchPost_Post_Processor", "settings").value)
assert saved2["operationsGrouping"] == 1 and saved2["clearFolder"] is True, saved2

# --- 5. browser selection: only Setup2 selected -> only Drill posted ---------
doc, prog = make_doc()
doc.products.itemByProductType("x").setups[1].isSelected = True
app.activeDocument = doc
shutil.rmtree(out); out.mkdir()
msgs, _ = click(config.QUICK_CMD_ID, [No])
t = target.read_text()
assert "(Drill)" in t and "(Face)" not in t, t
print("5 browser-selected setup only: ok")

# --- 6. rotated setup, A-axis off -> warned; Cancel stops -------------------
doc, prog = make_doc(rotated=True)
app.activeDocument = doc
shutil.rmtree(out); out.mkdir()
msgs, _ = click(config.QUICK_CMD_ID, [core.DialogResults.DialogCancel])
print("6 messages:", msgs)
assert "rotated relative" in msgs[0][1] and not target.exists()

# --- 7. no post processor -> clear message, nothing posted -------------------
doc, prog = make_doc()
prog.postConfiguration = None
app.activeDocument = doc
n = len(posts)
msgs, _ = click(config.QUICK_CMD_ID, [])
print("7 messages:", msgs)
assert ("post processor" in msgs[0][1]) and len(posts) == n

# --- 7b. dialog Process path (shared runner) ---------------------------------
from djr_batchpost.commands.postProcessor.dialog.dialog import PostDialog
from djr_batchpost.commands.postProcessor.settings.settings import Settings
from djr_batchpost.commands.postProcessor.programs import Programs
doc, prog = make_doc()
app.activeDocument = doc
shutil.rmtree(out); out.mkdir()
Settings.Load(doc.attributes); Programs.Load(doc.products.itemByProductType("x"))
assert Programs.Current._program is prog, "dialog did not preselect the only NC Program"
Settings.Set(Settings.OPERATIONS_GROUPING, Settings.OperationsGroupings.SETUP)
vals = {PostDialog._ROTATE_A_AXIS_ID: False, PostDialog._RESTORE_RAPID_MOVES_ID: True, PostDialog._RAPID_MOVES_MINIMUM_DISTANCE_ID: 20}
inputs = types.SimpleNamespace(itemById=lambda i: types.SimpleNamespace(value=vals[i]) if i in vals else None)
ui.messages.clear(); ui.answers = [No]
PostDialog.commandExecute(types.SimpleNamespace(command=types.SimpleNamespace(commandInputs=inputs)))
print("7b messages:", [(t, m.split("<")[0]) for t, m, _ in ui.messages])
written = sorted(p.relative_to(out).as_posix() for p in out.rglob("*.ngc"))
print("7b files:", written)
assert written == ["1001/Setup1.ngc", "1001/Setup2.ngc"], written
assert "Wrote 2 file(s)" in ui.messages[-1][1]
assert "G0 Z25" in (out / "1001/Setup1.ngc").read_text() or "Rapid" in (out / "1001/Setup1.ngc").read_text()
# second Process: clash on a multi-file grouping -> Yes retries once with overwrite
ui.messages.clear(); ui.answers = [Yes, No]
PostDialog.commandExecute(types.SimpleNamespace(command=types.SimpleNamespace(commandInputs=inputs)))
print("7b re-run:", [m.split("<")[0][:60] for t, m, _ in ui.messages])
assert "already exists" in ui.messages[0][1] and "Wrote 2 file(s)" in ui.messages[-1][1]
assert Settings(Settings.OVERWRITE_FILES) is False

# --- 8. stop removes both buttons -------------------------------------------
entry.stop(None)
assert [c.id for c in ui.panel._controls] == ["IronPostProcess"]
assert not ui.commandDefinitions._items
print("\nALL SIMULATION CHECKS PASSED")
