"""
"Post Combined": dialog-free posting to one combined G-code file.

Two ways in:
- the toolbar button posts the setups selected in the CAM browser (all
  setups if none are selected), into the NC Program's file name;
- right-clicking one or more setups shows "Post Combined" in the context
  menu, which posts exactly those setups. A single right-clicked setup is
  written to a file named after the setup.

If the document has no usable NC Program, one is created with the post
processor (and output folder) remembered from your last successful post.
"Single file" grouping is forced for the run only.
"""
from __future__ import annotations

import os

import adsk.core
import adsk.cam

from . import auto_program, config, post_runner, runtime_options
from .const import Const
from .programs import Programs
from .settings.settings import Settings
from .setups.setups import Setups
from .strings import Strings
from ...lib.fusionAddInUtils.general_utils import Utils
from ...lib.fusionAddInUtils.event_utils import Events

_SETUP_TYPE = "adsk::cam::Setup"


class QuickPostCommand:

    _local_handlers = []
    _menu_handler = None
    _pending_setups: list = []  # setups right-clicked for the context command
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
        # No command inputs: Fusion fires execute immediately, no dialog.
        command = args.command
        Events.add(command.execute, lambda a: cls.run(context_setups=None), local_handlers=cls._local_handlers)
        Events.add(command.destroy, cls.commandDestroy, local_handlers=cls._local_handlers)

    @classmethod
    def contextCommandCreated(cls, args: adsk.core.CommandCreatedEventArgs):
        setups, cls._pending_setups = list(cls._pending_setups), []
        command = args.command
        Events.add(command.execute, lambda a: cls.run(context_setups=setups), local_handlers=cls._local_handlers)
        Events.add(command.destroy, cls.commandDestroy, local_handlers=cls._local_handlers)

    @classmethod
    def commandDestroy(cls, args):
        cls._local_handlers = []

    # -------------------------------------------------------------------- run
    @classmethod
    def _ensure_program(cls, ui, cam) -> bool:
        """Make sure Programs.Current can post, creating an NC Program if needed."""
        program = Programs.Current
        if program is not None and program.canProcess:
            return True

        post, info = auto_program.resolve_post()
        if post is None:
            if info:
                msg = Strings("Couldn't find the post processor '{name}' you used last time in your post libraries.<p>Create an NC Program with your post processor in this document, then try again.").format(name=info.get('description', ''))
            else:
                msg = Strings("This document has no NC Program yet, and I don't know your post processor yet.<p>Create an NC Program once with your post processor and post with DJR Batch Post. After that, Post Combined creates the NC Program for you in any document.")
            ui.messageBox(msg, config.CMD_NAME)
            return False

        from .quick_post_helpers import program_file_name
        doc_name = Utils.sanitizeFilename(program_file_name(adsk.core.Application.get().activeDocument.name), preserveExtension=False)
        created = auto_program.create_program(cam, post, info, doc_name)
        Utils.log(f'QuickPost: created NC Program "{created.name}" with post "{getattr(post, "description", "")}".')
        Settings(Settings.NC_PROGRAM, created.name)
        Programs.Load(cam)
        if Programs.Current is None or not Programs.Current.canProcess:
            ui.messageBox(Strings("Created an NC Program, but it isn't ready to post. Open DJR Batch Post to check it."), config.CMD_NAME)
            return False
        return True

    @classmethod
    def run(cls, context_setups):
        app = adsk.core.Application.get()
        ui = app.userInterface
        doc = app.activeDocument

        product = doc.products.itemByProductType(Const.CAM_PRODUCT_ID) if doc is not None else None
        cam = adsk.cam.CAM.cast(product) if product is not None else None
        if cam is None:
            ui.messageBox(Strings("This document has no Manufacture (CAM) data to post."), config.CMD_NAME)
            return

        Settings.Load(doc.attributes)
        Strings.set_language(Settings(Settings.LANGUAGE))
        Programs.Load(cam)

        if not cls._ensure_program(ui, cam):
            Settings.Save(doc.attributes)
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

        program = Programs.Current
        saved_grouping = Settings(Settings.OPERATIONS_GROUPING)
        saved_clear = Settings(Settings.CLEAR_FOLDER)
        saved_file_name = program.fileName
        outputs = None
        try:
            # This run only: one combined file, never wipe the folder.
            Settings.Set(Settings.OPERATIONS_GROUPING, Settings.OperationsGroupings.SINGLE_FILE)
            Settings.Set(Settings.CLEAR_FOLDER, False)
            if context_setups and Setups.Count == 1:
                # One right-clicked setup -> file named after it.
                program.SetFileName(Utils.sanitizeFilename(Setups.selected[0].name, preserveExtension=False))
            runtime_options.sync_from_settings()
            outputs = post_runner.run_with_overwrite_prompt(ui)
        except Exception as e:
            Utils.log(f'QuickPost: error during post processing: {e}', adsk.core.LogLevels.ErrorLogLevel)
            ui.messageBox(f"An error occurred during post processing: {e}", "Error!",
                          adsk.core.MessageBoxButtonTypes.OKButtonType,
                          adsk.core.MessageBoxIconTypes.CriticalIconType)
        finally:
            program.SetFileName(saved_file_name)
            Settings.Set(Settings.OPERATIONS_GROUPING, saved_grouping)
            Settings.Set(Settings.CLEAR_FOLDER, saved_clear)
            Settings.Save(doc.attributes)

        if outputs is not None:
            post_runner.report_success(ui, outputs)
