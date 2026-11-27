"""
"Configure DJR Batch Post": choose the post processor and output folder
that Post Combined uses when it creates an NC Program, plus the default
G-code options for new documents. Optionally applies the post and folder to
the open document's NC Program too.

The button sits in Utilities → Add-Ins of the Manufacture workspace (falls
back to the Actions panel if that panel can't be found).
"""
from __future__ import annotations

import os
from pathlib import Path

import adsk.core
import adsk.cam

from . import auto_program, config, post_memory
from .const import Const
from .parameters import Parameters
from .programs import Programs
from .settings.settings import Settings
from ...lib.fusionAddInUtils.general_utils import Utils
from ...lib.fusionAddInUtils.event_utils import Events

# Utilities → Add-Ins panel. The exact id differs between workspaces and
# Fusion versions, so try the known ones and fall back to Actions.
_PANEL_CANDIDATES = ("CAMScriptsAddinsPanel", "SolidScriptsAddinsPanel")

_POST = "djr_cfg_post"
_INCLUDE_FUSION = "djr_cfg_include_fusion"
_FOLDER = "djr_cfg_folder"
_BROWSE = "djr_cfg_browse"
_APPLY_DOC = "djr_cfg_apply_doc"
_RAPIDS = "djr_cfg_rapids"
_RAPID_MIN = "djr_cfg_rapid_min"
_ROTATE_A = "djr_cfg_rotate_a"


def apply_configuration(post, output_folder: str, program, defaults: dict) -> list[str]:
    """
    Save the choices. ``program`` is the open document's Programs wrapper to
    update too, or None. Returns a list of what changed (for the message).
    No adsk imports are needed here, so it's unit testable.
    """
    changed = []
    if post is not None:
        post_memory.save(post_memory.describe_post(post, output_folder or None))
        changed.append(f"Post processor: {post_memory.post_label(post)}")
    elif output_folder:
        info = post_memory.load()
        if info:
            info["outputFolder"] = output_folder
            post_memory.save(info)
    if output_folder:
        changed.append(f"Output folder: {output_folder}")
    if defaults:
        Settings.UpdateDefaults(defaults)
        changed.append("Default G-code options for new documents")
    if program is not None:
        if post is not None:
            program._program.postConfiguration = post
        if output_folder:
            program.SetOutputFolder(Path(output_folder))
        changed.append(f"NC Program '{program.name}' in this document")
    return changed


class ConfigureCommand:

    _local_handlers = []
    _posts: list = []
    _program = None  # Programs wrapper of the open document, if any
    _ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dialog', 'resources_configure', '')

    # ------------------------------------------------------------------ setup
    @classmethod
    def _panel(cls, ui):
        panels = ui.workspaces.itemById(Const.CAM_WORKSPACE_ID).toolbarPanels
        for panel_id in _PANEL_CANDIDATES:
            try:
                panel = panels.itemById(panel_id)
            except Exception:
                panel = None
            if panel is not None:
                return panel
        return panels.itemById(Const.CAM_ACTIONS_PANEL_ID)

    @classmethod
    def start(cls):
        ui = adsk.core.Application.get().userInterface
        old = ui.commandDefinitions.itemById(config.CONFIG_CMD_ID)
        if old:
            try:
                old.deleteMe()
            except Exception:
                pass
        definition = ui.commandDefinitions.addButtonDefinition(
            config.CONFIG_CMD_ID, config.CONFIG_CMD_NAME, config.CONFIG_CMD_DESCRIPTION, cls._ICON_FOLDER)
        Events.add(definition.commandCreated, cls.commandCreated)
        panel = cls._panel(ui)
        old_control = panel.controls.itemById(config.CONFIG_CMD_ID)
        if old_control:
            try:
                old_control.deleteMe()
            except Exception:
                pass
        panel.controls.addCommand(definition)

    @classmethod
    def stop(cls):
        ui = adsk.core.Application.get().userInterface
        try:
            panel = cls._panel(ui)
            control = panel.controls.itemById(config.CONFIG_CMD_ID)
            if control:
                control.deleteMe()
        except Exception:
            pass
        definition = ui.commandDefinitions.itemById(config.CONFIG_CMD_ID)
        if definition:
            definition.deleteMe()

    # ------------------------------------------------------------------- UI
    @classmethod
    def _fill_posts(cls, dropdown, include_fusion: bool, info: dict):
        try:
            cls._posts = auto_program.available_posts(include_fusion)
        except Exception as e:
            Utils.log(f'Configure: could not read post libraries: {e}', adsk.core.LogLevels.WarningLogLevel)
            cls._posts = []
        if info and not any(post_memory.matches(p, info) for p in cls._posts) and not include_fusion:
            # The remembered post lives in Fusion's library: list it anyway.
            try:
                found, _ = auto_program.resolve_post()
                if found is not None:
                    cls._posts.insert(0, found)
            except Exception:
                pass
        items = dropdown.listItems
        items.clear()
        items.add("(keep current)", not info or not any(post_memory.matches(p, info) for p in cls._posts))
        for post in cls._posts:
            items.add(post_memory.post_label(post), bool(info) and post_memory.matches(post, info))

    @classmethod
    def commandCreated(cls, args: adsk.core.CommandCreatedEventArgs):
        app = adsk.core.Application.get()
        command = args.command
        command.setDialogInitialSize(520, 380)
        inputs = command.commandInputs
        info = post_memory.load()
        defaults = Settings.Defaults()

        current = info.get("description") if info else None
        inputs.addTextBoxCommandInput(
            "djr_cfg_note", "",
            "Used when Post Combined creates an NC Program."
            + (f"<br>Current post: <b>{current}</b>" if current else "<br>No post chosen yet."),
            2, True)
        post_input = inputs.addDropDownCommandInput(_POST, "Post processor", adsk.core.DropDownStyles.TextListDropDownStyle)
        inputs.addBoolValueInput(_INCLUDE_FUSION, "Include Fusion's built-in posts", True, "", False)
        cls._fill_posts(post_input, False, info)

        inputs.addStringValueInput(_FOLDER, "Output folder", info.get("outputFolder", "") if info else "")
        inputs.addBoolValueInput(_BROWSE, "Browse…", False, "", False)

        # Offer to update this document's NC Program too.
        cls._program = None
        doc = app.activeDocument
        product = doc.products.itemByProductType(Const.CAM_PRODUCT_ID) if doc is not None else None
        if product is not None:
            cam = adsk.cam.CAM.cast(product)
            Settings.Load(doc.attributes)
            Programs.Load(cam)
            cls._program = Programs.Current
        if cls._program is not None:
            inputs.addBoolValueInput(_APPLY_DOC, f"Also apply to NC Program '{cls._program.name}' in this document", True, "", True)

        group = inputs.addGroupCommandInput("djr_cfg_defaults", "Defaults for new documents")
        g = group.children
        g.addBoolValueInput(_RAPIDS, "Restore rapid moves", True, "", bool(defaults.get(Settings.RESTORE_RAPID_MOVES)))
        g.addFloatSpinnerCommandInput(_RAPID_MIN, "Minimum rapid move distance (mm)", "", 0, 1000, 1,
                                      float(defaults.get(Settings.RAPID_MOVES_MINIMUM_DISTANCE) or 20))
        g.addBoolValueInput(_ROTATE_A, "Rotate A-axis between setups", True, "", bool(defaults.get(Settings.ROTATE_A_AXIS)))

        Events.add(command.inputChanged, cls.inputChanged, local_handlers=cls._local_handlers)
        Events.add(command.execute, cls.commandExecute, local_handlers=cls._local_handlers)
        Events.add(command.destroy, cls.commandDestroy, local_handlers=cls._local_handlers)

    @classmethod
    def inputChanged(cls, args: adsk.core.InputChangedEventArgs):
        changed = args.input
        inputs = args.inputs
        if changed.id == _BROWSE:
            dialog = adsk.core.Application.get().userInterface.createFolderDialog()
            dialog.title = "Choose the output folder"
            if dialog.showDialog() == adsk.core.DialogResults.DialogOK:
                inputs.itemById(_FOLDER).value = dialog.folder
            changed.value = False
        elif changed.id == _INCLUDE_FUSION:
            cls._fill_posts(inputs.itemById(_POST), bool(changed.value), post_memory.load())

    @classmethod
    def commandExecute(cls, args: adsk.core.CommandEventArgs):
        ui = adsk.core.Application.get().userInterface
        inputs = args.command.commandInputs
        selected = inputs.itemById(_POST).selectedItem
        index = selected.index - 1 if selected is not None else -1  # item 0 is "(keep current)"
        post = cls._posts[index] if 0 <= index < len(cls._posts) else None
        folder = (inputs.itemById(_FOLDER).value or "").strip()
        apply_doc = inputs.itemById(_APPLY_DOC)
        program = cls._program if (apply_doc is not None and apply_doc.value) else None
        defaults = {
            Settings.RESTORE_RAPID_MOVES: bool(inputs.itemById(_RAPIDS).value),
            Settings.RAPID_MOVES_MINIMUM_DISTANCE: float(inputs.itemById(_RAPID_MIN).value),
            Settings.ROTATE_A_AXIS: bool(inputs.itemById(_ROTATE_A).value),
        }
        try:
            changed = apply_configuration(post, folder, program, defaults)
            if program is not None:
                Settings.Save(adsk.core.Application.get().activeDocument.attributes)
            ui.messageBox("Saved:<br>" + "<br>".join(changed), config.CONFIG_CMD_NAME)
        except Exception as e:
            Utils.log(f'Configure: {e}', adsk.core.LogLevels.ErrorLogLevel)
            ui.messageBox(f"Couldn't save the configuration: {e}", config.CONFIG_CMD_NAME)

    @classmethod
    def commandDestroy(cls, args):
        cls._local_handlers = []
        cls._posts = []
        cls._program = None
