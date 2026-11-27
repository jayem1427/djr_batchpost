"""
"Post Combined": post the chosen setups into one combined G-code file.

Two ways in:
- the toolbar button posts the setups selected in the CAM browser (all
  setups if none are selected);
- right-clicking one or more setups shows "Post Combined (DJR)", which posts
  exactly those setups.

Both open a small dialog: File (folder + name, pre-filled; one right-clicked
setup -> its name), Browse..., Post options..., then Post / Cancel.

If the document has a usable NC Program it is used (its post properties
apply). Otherwise a temporary NC Program is created with the post from
Configure DJR Batch Post / the last successful post, and deleted after the
run. "Post options..." keeps a persistent NC Program instead so the user can
edit its post settings. Grouping (Single file), clear-folder, file name and
output folder are overridden for the run only.
"""
from __future__ import annotations

import os
from pathlib import Path

import adsk.core
import adsk.cam

from . import auto_program, config, post_runner, runtime_options
from .const import Const
from .programs import Programs
from .settings.settings import Settings
from .setups.setups import Setups
from .strings import Strings
from .quick_post_helpers import join_target, program_file_name, split_target
from ...lib.fusionAddInUtils.general_utils import Utils
from ...lib.fusionAddInUtils.event_utils import Events

_SETUP_TYPE = "adsk::cam::Setup"



def _default_folder() -> Path:
    """Where to post when nothing is remembered yet: Documents, else home."""
    documents = Path.home() / "Documents"
    return documents if documents.is_dir() else Path.home()


_INFO = "djr_qp_info"
_FILE = "djr_qp_file"
_EXT = "djr_qp_ext"
_BROWSE = "djr_qp_browse"
_OPTIONS = "djr_qp_options"
_ERROR = "djr_qp_error"


class QuickPostCommand:

    _local_handlers = []
    _menu_handler = None
    _pending_setups: list = []  # setups right-clicked for the context command
    _plan = None                # what the open dialog will post
    _ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dialog', 'resources_quick', '')

    # ------------------------------------------------------------------ setup
    @classmethod
    def _definition(cls, ui, cmd_id: str, name: str, description: str, created):
        old = ui.commandDefinitions.itemById(cmd_id)
        if old:
            try:
                old.deleteMe()
            except Exception:
                Utils.log(f'QuickPost.start: could not delete stale definition {cmd_id}.', adsk.core.LogLevels.WarningLogLevel)
        definition = ui.commandDefinitions.itemById(cmd_id)
        if definition is None:
            definition = ui.commandDefinitions.addButtonDefinition(cmd_id, name, description, cls._ICON_FOLDER)
        Events.add(definition.commandCreated, created)
        return definition

    @classmethod
    def start(cls):
        ui = adsk.core.Application.get().userInterface
        panel = ui.workspaces.itemById(Const.CAM_WORKSPACE_ID).toolbarPanels.itemById(Const.CAM_ACTIONS_PANEL_ID)

        old_control = panel.controls.itemById(config.QUICK_CMD_ID)
        if old_control:
            try:
                old_control.deleteMe()
            except Exception:
                Utils.log('QuickPost.start: could not delete stale control.', adsk.core.LogLevels.WarningLogLevel)

        cmd_def = cls._definition(ui, config.QUICK_CMD_ID, config.QUICK_CMD_NAME,
                                  config.QUICK_CMD_DESCRIPTION, cls.commandCreated)
        cls._definition(ui, config.QUICK_CTX_CMD_ID, config.QUICK_CTX_CMD_NAME,
                        config.QUICK_CTX_CMD_DESCRIPTION, cls.contextCommandCreated)

        control = panel.controls.itemById(config.QUICK_CMD_ID)
        if control is None:
            try:
                control = panel.controls.addCommand(cmd_def, config.CMD_ID, False)  # after the dialog button
            except Exception:
                control = panel.controls.addCommand(cmd_def)
        control.isPromoted = True

        # Right-click menu entry on setups.
        cls._menu_handler = Events.add(ui.markingMenuDisplaying, cls.markingMenuDisplaying)

    @classmethod
    def stop(cls):
        ui = adsk.core.Application.get().userInterface
        if cls._menu_handler is not None:
            try:
                ui.markingMenuDisplaying.remove(cls._menu_handler)
            except Exception:
                pass
            cls._menu_handler = None
        panel = ui.workspaces.itemById(Const.CAM_WORKSPACE_ID).toolbarPanels.itemById(Const.CAM_ACTIONS_PANEL_ID)
        control = panel.controls.itemById(config.QUICK_CMD_ID)
        if control:
            control.deleteMe()
        for cmd_id in (config.QUICK_CMD_ID, config.QUICK_CTX_CMD_ID):
            definition = ui.commandDefinitions.itemById(cmd_id)
            if definition:
                definition.deleteMe()

    # ------------------------------------------------------------ right-click
    @classmethod
    def markingMenuDisplaying(cls, args):
        setups = [e for e in (args.selectedEntities or []) if getattr(e, 'objectType', '') == _SETUP_TYPE]
        if not setups:
            return
        cls._pending_setups = setups
        ui = adsk.core.Application.get().userInterface
        definition = ui.commandDefinitions.itemById(config.QUICK_CTX_CMD_ID)
        controls = args.linearMarkingMenu.controls
        if definition is not None and controls.itemById(config.QUICK_CTX_CMD_ID) is None:
            controls.addSeparator(config.QUICK_CTX_CMD_ID + '_separator')
            controls.addCommand(definition)

    # ---------------------------------------------------------------- commands
    @classmethod
    def commandCreated(cls, args: adsk.core.CommandCreatedEventArgs):
        cls._open(args.command, None)

    @classmethod
    def contextCommandCreated(cls, args: adsk.core.CommandCreatedEventArgs):
        setups, cls._pending_setups = list(cls._pending_setups), []
        cls._open(args.command, setups)

    @classmethod
    def commandDestroy(cls, args):
        cls._local_handlers = []
        cls._plan = None

    # ------------------------------------------------------------- the dialog
    @classmethod
    def _prepare(cls, context_setups):
        """Work out what will be posted and the default file. None = can't post
        (the reason has been shown)."""
        app = adsk.core.Application.get()
        ui = app.userInterface
        doc = app.activeDocument
        product = doc.products.itemByProductType(Const.CAM_PRODUCT_ID) if doc is not None else None
        cam = adsk.cam.CAM.cast(product) if product is not None else None
        if cam is None:
            ui.messageBox(Strings("This document has no Manufacture (CAM) data to post."), config.CMD_NAME)
            return None

        Settings.Load(doc.attributes)
        Strings.set_language(Settings(Settings.LANGUAGE))
        Programs.Load(cam)

        plan = {"cam": cam, "doc": doc, "context": context_setups, "post": None, "info": {}}
        program = Programs.Current
        if program is not None and program.canProcess:
            plan.update(program=program, folder=program.GetOutputFolder(), name=program.fileName,
                        ext=program.fileExtension or "", postName=program.postProcessorDescription)
        else:
            post, info = auto_program.resolve_post()
            if post is None:
                if info:
                    msg = Strings("Couldn't find the post processor '{name}' you used last time in your post libraries.<p>Create an NC Program with your post processor in this document, then try again.").format(name=info.get('description', ''))
                else:
                    msg = Strings("No post processor chosen yet.<p>Open Utilities > Add-Ins > Configure DJR Batch Post and pick your post processor, then try again.")
                ui.messageBox(msg, config.CMD_NAME)
                return None
            ext = getattr(post, "extension", "") or info.get("extension", "")
            if ext and not ext.startswith("."):
                ext = "." + ext
            plan.update(program=None, post=post, info=info,
                        folder=Path(info.get("outputFolder") or _default_folder()),
                        name=program_file_name(doc.name), ext=ext,
                        postName=getattr(post, "description", ""))
        if context_setups and len(context_setups) == 1:
            plan["name"] = context_setups[0].name
        plan["name"] = Utils.sanitizeFilename(plan["name"] or "program", preserveExtension=False)
        return plan

    @classmethod
    def _info_text(cls, plan) -> str:
        post = plan.get("postName") or "?"
        if plan["program"] is None:
            return Strings("Posts with <b>{post}</b> through a temporary NC Program that is removed afterwards. <b>Post options…</b> keeps an NC Program in this document so you can change post settings (e.g. 4th axis).").format(post=post)
        return Strings("Posts with <b>{post}</b> using NC Program <b>{program}</b>. <b>Post options…</b> opens it to change post settings.").format(post=post, program=plan["program"].name)

    @classmethod
    def _open(cls, command, context_setups):
        cls._plan = plan = cls._prepare(context_setups)
        Events.add(command.destroy, cls.commandDestroy, local_handlers=cls._local_handlers)
        Events.add(command.execute, cls.commandExecute, local_handlers=cls._local_handlers)
        if plan is None:
            return  # no inputs: Fusion runs execute at once, which does nothing
        command.okButtonText = Strings("Post")
        command.setDialogInitialSize(520, 240)
        inputs = command.commandInputs
        inputs.addTextBoxCommandInput(_INFO, "", cls._info_text(plan), 3, True)
        inputs.addStringValueInput(_FILE, Strings("File"), join_target(plan["folder"], plan["name"]))
        inputs.addTextBoxCommandInput(_EXT, Strings("Extension"), plan["ext"] or "-", 1, True)
        inputs.addBoolValueInput(_BROWSE, Strings("Browse…"), False, "", False)
        inputs.addBoolValueInput(_OPTIONS, Strings("Post options…"), False, "", False)
        inputs.addTextBoxCommandInput(_ERROR, "", "", 1, True)
        Events.add(command.inputChanged, cls.inputChanged, local_handlers=cls._local_handlers)
        Events.add(command.validateInputs, cls.validateInputs, local_handlers=cls._local_handlers)

    @classmethod
    def _target(cls, inputs):
        ext = cls._plan["ext"] if cls._plan else ""
        return split_target(inputs.itemById(_FILE).value, ext,
                            lambda n: Utils.sanitizeFilename(n, preserveExtension=False))

    @classmethod
    def validateInputs(cls, args):
        if cls._plan is None:
            return
        _, _, error = cls._target(args.inputs)
        args.areInputsValid = error is None
        box = args.inputs.itemById(_ERROR)
        if box is not None:
            box.formattedText = f'<span style="color:#c0392b">{Strings(error)}</span>' if error else ""

    @classmethod
    def inputChanged(cls, args):
        changed = args.input
        if cls._plan is None:
            return
        if changed.id == _BROWSE:
            changed.value = False
            cls._browse(args.inputs)
        elif changed.id == _OPTIONS:
            changed.value = False
            cls._post_options(args.inputs)

    @classmethod
    def _browse(cls, inputs):
        plan = cls._plan
        folder, name, _ = cls._target(inputs)
        dialog = adsk.core.Application.get().userInterface.createFileDialog()
        dialog.title = Strings("Save G-code as")
        ext = plan["ext"] or ""
        dialog.filter = f"G-code (*{ext})" if ext else "All files (*.*)"
        dialog.initialDirectory = str(folder or plan["folder"])
        dialog.initialFilename = (name or plan["name"]) + ext
        if dialog.showSave() == adsk.core.DialogResults.DialogOK:
            chosen = dialog.filename
            if ext and chosen.lower().endswith(ext.lower()):
                chosen = chosen[: -len(ext)]
            inputs.itemById(_FILE).value = chosen

    @classmethod
    def _post_options(cls, inputs):
        """Keep an NC Program in this document and point the user at it, so
        Fusion's own NC Program dialog (post properties) is one step away."""
        plan = cls._plan
        ui = adsk.core.Application.get().userInterface
        program = plan["program"]
        try:
            if program is None:
                created = auto_program.create_program(plan["cam"], plan["post"], plan["info"], plan["name"],
                                                      auto_program.AUTO_PROGRAM_NAME)
                Settings(Settings.NC_PROGRAM, created.name)
                Settings.Save(plan["doc"].attributes)
                Programs.Load(plan["cam"])
                program = Programs.Current
                plan["program"] = program
                inputs.itemById(_INFO).formattedText = cls._info_text(plan)
            ui.activeSelections.clear()
            ui.activeSelections.add(program._program)
        except Exception as e:
            Utils.log(f'QuickPost: Post options failed: {e}', adsk.core.LogLevels.ErrorLogLevel)
            ui.messageBox(f"Couldn't prepare the NC Program: {e}", config.CMD_NAME)
            return
        ui.messageBox(Strings("NC Program <b>{program}</b> is selected in the browser and will be used for every post in this document.<p>Close this dialog, then double-click the NC Program (or right-click > Edit) to change post settings such as the 4th axis. Post again when you're done.").format(program=program.name),
                      config.CMD_NAME)

    @classmethod
    def commandExecute(cls, args):
        plan = cls._plan
        if plan is None:
            return
        folder, name, error = cls._target(args.command.commandInputs)
        if error:
            adsk.core.Application.get().userInterface.messageBox(Strings(error), config.CMD_NAME)
            return
        cls.run(plan, folder, name)

    # -------------------------------------------------------------------- run
    @classmethod
    def run(cls, plan, folder: Path, name: str):
        ui = adsk.core.Application.get().userInterface
        cam, doc, context_setups = plan["cam"], plan["doc"], plan["context"]
        temp = None
        saved_nc_program = Settings(Settings.NC_PROGRAM)
        saved_grouping = Settings(Settings.OPERATIONS_GROUPING)
        saved_clear = Settings(Settings.CLEAR_FOLDER)
        program = plan["program"]
        saved_file_name = saved_folder = None
        try:
            if program is None:
                temp = auto_program.create_program(cam, plan["post"], plan["info"], name,
                                                   auto_program.TEMP_PROGRAM_NAME)
                Settings(Settings.NC_PROGRAM, temp.name)
                Programs.Load(cam)
                program = Programs.Current
                if program is None or not program.canProcess:
                    ui.messageBox(Strings("Created an NC Program, but it isn't ready to post. Open DJR Batch Post to check it."), config.CMD_NAME)
                    return
            if context_setups:
                if Setups.SelectOnly(context_setups) == 0:
                    ui.messageBox(Strings("Couldn't find the right-clicked setup. Try again."), config.CMD_NAME)
                    return
            if not Setups.hasSelected or Setups.Count == 0:
                ui.messageBox(Strings("No setups to post. Unsuppress a setup or fix its errors, then try again."), config.CMD_NAME)
                return

            rotate = bool(Settings(Settings.ROTATE_A_AXIS))
            if not post_runner.confirm_safety(ui, rotate):
                return
            if not post_runner.confirm_rotated_setups_without_a_axis(ui, rotate):
                return

            # This run only: one combined file at the chosen path, never wipe the folder.
            saved_file_name, saved_folder = program.fileName, program.GetOutputFolder()
            Settings.Set(Settings.OPERATIONS_GROUPING, Settings.OperationsGroupings.SINGLE_FILE)
            Settings.Set(Settings.CLEAR_FOLDER, False)
            folder.mkdir(parents=True, exist_ok=True)
            program.SetFileName(name)
            program.SetOutputFolder(Path(folder))
            runtime_options.sync_from_settings()
            outputs = post_runner.run_with_overwrite_prompt(ui)
            if outputs is not None:
                post_runner.report_success(ui, outputs)
        except Exception as e:
            Utils.log(f'QuickPost: error during post processing: {e}', adsk.core.LogLevels.ErrorLogLevel)
            ui.messageBox(f"An error occurred during post processing: {e}", "Error!",
                          adsk.core.MessageBoxButtonTypes.OKButtonType,
                          adsk.core.MessageBoxIconTypes.CriticalIconType)
        finally:
            if temp is None and program is not None and saved_file_name is not None:
                program.SetFileName(saved_file_name)
                program.SetOutputFolder(saved_folder)
            Settings.Set(Settings.OPERATIONS_GROUPING, saved_grouping)
            Settings.Set(Settings.CLEAR_FOLDER, saved_clear)
            if temp is not None:
                Settings(Settings.NC_PROGRAM, saved_nc_program)
                auto_program.delete_program(temp)
            Settings.Save(doc.attributes)
