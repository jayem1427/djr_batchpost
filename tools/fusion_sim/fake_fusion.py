"""A behavioural fake of the slice of the Fusion API the add-in touches."""
from __future__ import annotations

import math
import sys
import types
from pathlib import Path


def install(posts_log: list):
    adsk = types.ModuleType("adsk")
    core = types.ModuleType("adsk.core")
    cam = types.ModuleType("adsk.cam")

    def enum(**kw):
        return type("E", (), kw)

    core.LogLevels = enum(InfoLogLevel=0, WarningLogLevel=1, ErrorLogLevel=2)
    core.LogTypes = enum(FileLogType=0, ConsoleLogType=1)
    core.MessageBoxButtonTypes = enum(OKButtonType=0, OKCancelButtonType=1, YesNoButtonType=3)
    core.MessageBoxIconTypes = enum(NoIconIconType=0, QuestionIconType=1, InformationIconType=2, WarningIconType=3, CriticalIconType=4)
    core.DialogResults = enum(DialogOK=0, DialogCancel=1, DialogYes=2, DialogNo=3)
    core.DropDownStyles = enum(TextListDropDownStyle=0)
    core.TablePresentationStyles = enum(transparentBackgroundTablePresentationStyle=0)

    # ---- geometry -------------------------------------------------------
    class Vector3D:
        def __init__(self, x, y, z):
            self.x, self.y, self.z = x, y, z

        @staticmethod
        def create(x, y, z):
            return Vector3D(x, y, z)

        def transformBy(self, m):
            r = m.rot
            self.x, self.y, self.z = (r[0][0]*self.x + r[0][1]*self.y + r[0][2]*self.z,
                                      r[1][0]*self.x + r[1][1]*self.y + r[1][2]*self.z,
                                      r[2][0]*self.x + r[2][1]*self.y + r[2][2]*self.z)

        @property
        def length(self):
            return math.sqrt(self.x**2 + self.y**2 + self.z**2)

        def normalize(self):
            l = self.length
            if l:
                self.x, self.y, self.z = self.x/l, self.y/l, self.z/l

        def dotProduct(self, o):
            return self.x*o.x + self.y*o.y + self.z*o.z

        def crossProduct(self, o):
            return Vector3D(self.y*o.z - self.z*o.y, self.z*o.x - self.x*o.z, self.x*o.y - self.y*o.x)

        def isParallelTo(self, o):
            return self.crossProduct(o).length < 1e-9

    class Point3D(Vector3D):
        @staticmethod
        def create(x, y, z):
            return Point3D(x, y, z)

        def transformBy(self, m):
            Vector3D.transformBy(self, m)
            self.x += m.t[0]; self.y += m.t[1]; self.z += m.t[2]

        def isEqualTo(self, o):
            return abs(self.x-o.x) + abs(self.y-o.y) + abs(self.z-o.z) < 1e-9

    core.Vector3D = Vector3D
    core.Point3D = Point3D

    # ---- events -----------------------------------------------------------
    class CommandCreatedEventHandler:  # base classes the add-in subclasses
        pass

    class CommandEventHandler:
        pass

    class InputChangedEventHandler:
        pass

    class ValidateInputsEventHandler:
        pass

    class MarkingMenuEventHandler:
        pass

    for cls in (CommandCreatedEventHandler, CommandEventHandler, InputChangedEventHandler, ValidateInputsEventHandler, MarkingMenuEventHandler):
        setattr(core, cls.__name__, cls)

    def make_event(handler_type_name):
        def add(self, handler):
            self.handlers.append(handler)
            return True
        add.__annotations__ = {"handler": handler_type_name}
        ev_cls = type("Event_" + handler_type_name, (), {"add": add, "__module__": "adsk.core"})

        def init(self):
            self.handlers = []
        ev_cls.__init__ = init

        def remove(self, handler):
            self.handlers.remove(handler)
            return True
        ev_cls.remove = remove

        def fire(self, args):
            for h in list(self.handlers):
                h.notify(args)
        ev_cls.fire = fire
        return ev_cls()

    # ---- UI ---------------------------------------------------------------
    class Control:
        def __init__(self, panel, definition):
            self.panel, self.definition, self.id = panel, definition, definition.id
            self.isPromoted = False

        def deleteMe(self):
            self.panel._controls.remove(self)
            return True

    class Controls:
        def __init__(self, panel):
            self.panel = panel

        def itemById(self, id_):
            return next((c for c in self.panel._controls if c.id == id_), None)

        def addCommand(self, definition, positionID="", isBefore=True):
            c = Control(self.panel, definition)
            if positionID:
                idx = next(i for i, x in enumerate(self.panel._controls) if x.id == positionID)  # raises like Fusion would complain
                self.panel._controls.insert(idx + (0 if isBefore else 1), c)
            else:
                self.panel._controls.append(c)
            return c

    class Panel:
        def __init__(self):
            self._controls = []
            self.controls = Controls(self)
            Controls.addCommand(self.controls, types.SimpleNamespace(id="IronPostProcess"))

    class CommandDefinition:
        def __init__(self, defs, id_, name, tooltip, resources):
            self.defs, self.id, self.name, self.tooltip, self.resourceFolder = defs, id_, name, tooltip, resources
            self.commandCreated = make_event("CommandCreatedEventHandler")

        def deleteMe(self):
            self.defs._items.pop(self.id)
            return True

        def execute(self):
            UI.instance.run_command(self)

    class CommandDefinitions:
        def __init__(self):
            self._items = {}

        def itemById(self, id_):
            return self._items.get(id_)

        def addButtonDefinition(self, id_, name, tooltip, resources):
            if id_ in self._items:
                raise RuntimeError("duplicate id")
            d = CommandDefinition(self, id_, name, tooltip, resources)
            self._items[id_] = d
            return d

    class Command:
        def __init__(self):
            self.execute = make_event("CommandEventHandler")
            self.destroy = make_event("CommandEventHandler")
            self.inputChanged = make_event("InputChangedEventHandler")
            self.validateInputs = make_event("ValidateInputsEventHandler")
            self.inputs_created = 0

    class UI:
        instance = None

        def __init__(self):
            UI.instance = self
            self.panel = Panel()
            self.workspaces = types.SimpleNamespace(itemById=lambda i: types.SimpleNamespace(
                toolbarPanels=types.SimpleNamespace(itemById=lambda p: self.panel)))
            self.commandDefinitions = CommandDefinitions()
            self.messages = []
            self.answers = []  # queue of DialogResults to return
            self.markingMenuDisplaying = make_event("MarkingMenuEventHandler")

        def right_click(self, entities):
            """Fire markingMenuDisplaying and return the linear menu's control ids."""
            panel = Panel()
            panel._controls.clear()
            menu = types.SimpleNamespace(controls=panel.controls)
            def addSeparator(id_="", positionID="", isBefore=True):
                panel._controls.append(types.SimpleNamespace(id=id_ or "sep"))
            panel.controls.addSeparator = addSeparator
            self.markingMenuDisplaying.fire(types.SimpleNamespace(selectedEntities=list(entities), linearMarkingMenu=menu))
            return [c.id for c in panel._controls]

        def messageBox(self, text, title="", buttons=0, icon=0):
            self.messages.append((title, text, buttons))
            if self.answers:
                return self.answers.pop(0)
            return core.DialogResults.DialogOK

        def run_command(self, definition):
            """Mimic Fusion: created -> (no inputs => execute immediately) -> destroy."""
            cmd = Command()
            definition.commandCreated.fire(types.SimpleNamespace(command=cmd))
            cmd.execute.fire(types.SimpleNamespace(command=cmd))
            cmd.destroy.fire(types.SimpleNamespace(command=cmd))

    # ---- document / CAM -----------------------------------------------------
    class Attributes:
        def __init__(self):
            self._d = {}

        @property
        def count(self):
            return len(self._d)

        def itemByName(self, g, n):
            return self._d.get((g, n))

        def add(self, g, n, v):
            self._d[(g, n)] = types.SimpleNamespace(value=v)
            return self._d[(g, n)]

    class Param:
        def __init__(self, v):
            self.value = types.SimpleNamespace(value=v)

    class Params:
        def __init__(self, d):
            self._d = {k: Param(v) for k, v in d.items()}

        def itemByName(self, n):
            return self._d.get(n)

    class Matrix:
        def __init__(self, rot, t=(0, 0, 0)):
            self.rot, self.t = rot, t

    IDENT = Matrix([[1, 0, 0], [0, 1, 0], [0, 0, 1]])

    class Tool:
        def __init__(self, number, desc):
            self.parameters = Params({"tool_number": number})
            self.description = desc

    class Op:
        def __init__(self, name, tool):
            self.name, self.tool = name, tool
            self.isSuppressed = False
            self.hasToolpath = True

    class FakeSetup:
        def __init__(self, name, ops, wcs=IDENT, selected=False):
            self.name, self.allOperations, self.workCoordinateSystem = name, ops, wcs
            self.isSelected, self.isSuppressed, self.hasError, self.machine = selected, False, False, None
            self.objectType = 'adsk::cam::Setup'

    class NCProgram:
        def __init__(self, name, out_folder, file_name):
            self.name, self.hasError, self.isSuppressed, self.hasWarning, self.warning = name, False, False, False, ""
            self.isSelected = False
            self.operations = ["placeholder-op"]
            self.attributes = Attributes()
            self.machine = None
            self.postConfiguration = types.SimpleNamespace(description="LinuxCNC (fake)", extension=".ngc")
            self.parameters = Params({
                "nc_program_filename": file_name,
                "nc_program_openInEditor": True,
                "nc_program_output_folder": str(out_folder),
                "nc_program_name": name,
                "nc_program_nc_extension": ".ngc",
            })

        def postProcess(self, options):
            p = self.parameters
            folder = Path(p.itemByName("nc_program_output_folder").value.value)
            name = p.itemByName("nc_program_filename").value.value
            lines = ["%", "(fake post)", ]
            for op in self.operations:
                lines.append(f"(T{op.tool.parameters.itemByName('tool_number').value.value} {op.tool.description})")
            lines += ["G90 G94 G17", "G21"]
            for op in self.operations:
                t = op.tool.parameters.itemByName('tool_number').value.value
                lines += [f"({op.name})", "M9", f"T{t} M6", "S12000 M3", "G0 X0 Y0", "G0 Z5", "G1 Z-1 F300",
                          "G1 X10 Y0 F800", "G1 Z25 F800", "G1 X60 Y40 F800", "G1 Z-1 F800", "G1 X70 F800", "G0 Z5"]
            lines += ["M5", "M9", "M30", "%"]
            (folder / f"{name}.ngc").write_text("\n".join(lines) + "\n")
            posts_log.append([op.name for op in self.operations])
            return True

    class NCProgramInput:
        def __init__(self):
            self.displayName = ""
            self.operations = []
            self.parameters = Params({
                "nc_program_filename": "1001",
                "nc_program_openInEditor": True,
                "nc_program_output_folder": str(DEFAULT_OUT[0]),
                "nc_program_name": "",
                "nc_program_nc_extension": "",
            })

    class NCPrograms(list):
        def createInput(self):
            return NCProgramInput()

        def add(self, inp):
            p = NCProgram(inp.displayName, inp.parameters.itemByName("nc_program_output_folder").value.value,
                          inp.parameters.itemByName("nc_program_filename").value.value)
            p.parameters = inp.parameters
            p.operations = list(inp.operations)
            p.postConfiguration = None
            self.append(p)
            return p

    class CAMProduct:
        def __init__(self, programs, setups):
            self.ncPrograms, self.setups = NCPrograms(programs), setups

        def checkToolpath(self, setup):
            return True

    class Document:
        def __init__(self, cam_product, name="Test Bracket v7"):
            self.name = name
            self.attributes = Attributes()
            self.products = types.SimpleNamespace(itemByProductType=lambda t: cam_product)

    class Application:
        _inst = None

        @staticmethod
        def get():
            if Application._inst is None:
                Application._inst = Application()
            return Application._inst

        def __init__(self):
            self.userInterface = UI()
            self.activeDocument = None

        def log(self, *a, **k):
            pass

    core.Application = Application
    for name in ("CommandCreatedEventArgs", "CommandEventArgs", "InputChangedEventArgs", "ValidateInputsEventArgs",
                 "CommandInput", "BoolValueCommandInput", "DropDownCommandInput", "StringValueCommandInput",
                 "TextBoxCommandInput", "Attributes", "Event", "Command", "CommandInputs"):
        setattr(core, name, object)

    class CAM:
        @staticmethod
        def cast(x):
            return x

    cam.LibraryLocations = enum(LocalLibraryLocation=0, CloudLibraryLocation=1, NetworkLibraryLocation=2,
                                OnlineSamplesLibraryLocation=3, ExternalLibraryLocation=4, Fusion360LibraryLocation=5)

    class PostLibrary:
        def __init__(self):
            self.tree = {}  # url -> {"posts": [...], "folders": [urls]}

        def urlByLocation(self, loc):
            return f"loc{loc}://"

        def childPostConfigurations(self, url):
            return self.tree.get(url, {}).get("posts", [])

        def childFolderURLs(self, url):
            return self.tree.get(url, {}).get("folders", [])

    POST_LIBRARY = PostLibrary()
    cam.CAMManager = types.SimpleNamespace(get=lambda: types.SimpleNamespace(
        libraryManager=types.SimpleNamespace(postLibrary=POST_LIBRARY)))

    cam.CAM = CAM
    cam.NCProgramPostProcessOptions = types.SimpleNamespace(create=staticmethod(lambda: object()))
    for name in ("NCProgram", "Setup", "Setups", "Operation", "Tool", "NCParameters"):
        setattr(cam, name, object)

    DEFAULT_OUT = [Path('.')]
    adsk.core, adsk.cam = core, cam
    sys.modules.update({"adsk": adsk, "adsk.core": core, "adsk.cam": cam})
    return types.SimpleNamespace(core=core, cam=cam, Matrix=Matrix, Tool=Tool, Op=Op, Setup=FakeSetup,
                                 NCProgram=NCProgram, CAMProduct=CAMProduct, Document=Document, POST_LIBRARY=POST_LIBRARY, DEFAULT_OUT=DEFAULT_OUT,
                                 Application=Application)
