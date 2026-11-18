"""
"Post Combined": a dialog-free button that posts straight to one
combined G-code file.

It uses whatever the DJR Batch Post dialog last saved in the document
(NC Program, output folder, file name, G-code options) and forces
"Single file" grouping for this run only. Setups selected in the CAM
browser are posted; with none selected, every setup is.
"""
from __future__ import annotations

import os

import adsk.core
import adsk.cam

from . import config, post_runner, runtime_options
from .const import Const
from .programs import Programs
from .settings.settings import Settings
from .setups.setups import Setups
from .strings import Strings
from ...lib.fusionAddInUtils.general_utils import Utils
from ...lib.fusionAddInUtils.event_utils import Events


class QuickPostCommand:

    _local_handlers = []
    _ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dialog', 'resources_quick', '')

    @classmethod
    def start(cls):
        ui = adsk.core.Application.get().userInterface
        panel = ui.workspaces.itemById(Const.CAM_WORKSPACE_ID).toolbarPanels.itemById(Const.CAM_ACTIONS_PANEL_ID)

        # Clear leftovers from a previous run of the add-in.
        old_control = panel.controls.itemById(config.QUICK_CMD_ID)
        if old_control:
            try:
                old_control.deleteMe()
            except Exception:
                Utils.log('QuickPost.start: could not delete stale control.', adsk.core.LogLevels.WarningLogLevel)
        old_definition = ui.commandDefinitions.itemById(config.QUICK_CMD_ID)
        if old_definition:
            try:
                old_definition.deleteMe()
            except Exception:
                Utils.log('QuickPost.start: could not delete stale definition.', adsk.core.LogLevels.WarningLogLevel)

        cmd_def = ui.commandDefinitions.itemById(config.QUICK_CMD_ID)
        if cmd_def is None:
            cmd_def = ui.commandDefinitions.addButtonDefinition(
                config.QUICK_CMD_ID,
                config.QUICK_CMD_NAME,
                config.QUICK_CMD_DESCRIPTION,
                cls._ICON_FOLDER,
            )
        Events.add(cmd_def.commandCreated, cls.commandCreated)

        control = panel.controls.itemById(config.QUICK_CMD_ID)
        if control is None:
            try:
                # Right after the DJR Batch Post button.
                control = panel.controls.addCommand(cmd_def, config.CMD_ID, False)
            except Exception:
                control = panel.controls.addCommand(cmd_def)
        control.isPromoted = True

    @classmethod
    def stop(cls):
        ui = adsk.core.Application.get().userInterface
        panel = ui.workspaces.itemById(Const.CAM_WORKSPACE_ID).toolbarPanels.itemById(Const.CAM_ACTIONS_PANEL_ID)
        control = panel.controls.itemById(config.QUICK_CMD_ID)
        if control:
            control.deleteMe()
        definition = ui.commandDefinitions.itemById(config.QUICK_CMD_ID)
        if definition:
            definition.deleteMe()

    @classmethod
    def commandCreated(cls, args: adsk.core.CommandCreatedEventArgs):
        # No command inputs are added, so Fusion fires execute immediately
        # and no dialog is shown.
        command = args.command
        Events.add(command.execute, cls.commandExecute, local_handlers=cls._local_handlers)
        Events.add(command.destroy, cls.commandDestroy, local_handlers=cls._local_handlers)

    @classmethod
    def commandDestroy(cls, args):
        cls._local_handlers = []

    @classmethod
    def commandExecute(cls, args: adsk.core.CommandEventArgs):
        app = adsk.core.Application.get()
        ui = app.userInterface
        doc = app.activeDocument
        title = config.CMD_NAME

        product = doc.products.itemByProductType(Const.CAM_PRODUCT_ID) if doc is not None else None
        cam = adsk.cam.CAM.cast(product) if product is not None else None
        if cam is None:
            ui.messageBox(Strings("This document has no Manufacture (CAM) data to post."), title)
            return

        Settings.Load(doc.attributes)
        Strings.set_language(Settings(Settings.LANGUAGE))
        Programs.Load(cam)

        program = Programs.Current
        if program is None:
            ui.messageBox(Strings("No usable NC Program found.<p>Create an NC Program (with at least one operation) and pick your post processor, then try again."), title)
            return
        if not program.canProcess:
            ui.messageBox(Strings("The NC Program '{name}' has no post processor.<p>Edit the NC Program, pick your .cps post processor, then try again.").format(name=program.name), title)
            return
        if not Setups.hasSelected or Setups.Count == 0:
            ui.messageBox(Strings("No setups to post. Unsuppress a setup or fix its errors, then try again."), title)
            return

        rotate = bool(Settings(Settings.ROTATE_A_AXIS))
        if not post_runner.confirm_safety(ui, rotate):
            return
        if not post_runner.confirm_rotated_setups_without_a_axis(ui, rotate):
            return

        saved_grouping = Settings(Settings.OPERATIONS_GROUPING)
        saved_clear = Settings(Settings.CLEAR_FOLDER)
        outputs = None
        try:
            # This run only: one combined file, and never wipe the folder.
            Settings.Set(Settings.OPERATIONS_GROUPING, Settings.OperationsGroupings.SINGLE_FILE)
            Settings.Set(Settings.CLEAR_FOLDER, False)
            runtime_options.sync_from_settings()
            outputs = post_runner.run_with_overwrite_prompt(ui)
        except Exception as e:
            Utils.log(f'QuickPost: error during post processing: {e}', adsk.core.LogLevels.ErrorLogLevel)
            ui.messageBox(f"An error occurred during post processing: {e}", "Error!",
                          adsk.core.MessageBoxButtonTypes.OKButtonType,
                          adsk.core.MessageBoxIconTypes.CriticalIconType)
        finally:
            Settings.Set(Settings.OPERATIONS_GROUPING, saved_grouping)
            Settings.Set(Settings.CLEAR_FOLDER, saved_clear)
            Settings.Save(doc.attributes)

        if outputs is not None:
            post_runner.report_success(ui, outputs)
