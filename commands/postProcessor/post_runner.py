"""
The posting run shared by the Batch Post dialog and the one-click
"Post Combined" command: safety prompts, the post itself, the
overwrite prompt, and the completion message.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Optional

import adsk.core

from . import config, run_report
from .programs import Programs
from .setups.setups import Setups
from .settings.settings import Settings
from .strings import Strings
from .validation_helpers import should_warn_machine_lacks_a_axis
from .quick_post_helpers import (
    combined_output_path,
    common_folder,
    describe_outputs,
    open_in_file_browser,
)
from ...lib.fusionAddInUtils.general_utils import Utils


def confirm_safety(ui, rotate_a_axis: bool) -> bool:
    """Show the WCS / A-axis warnings. Returns False if the user cancels."""
    alignedWCS, badOrigins, badXAxes = Setups.getWCSAlignmentIssues()
    if not alignedWCS and Setups.Count > 1:
        Utils.log(f'PostRunner: WCS are not aligned for setups: {badOrigins} {badXAxes}', adsk.core.LogLevels.ErrorLogLevel)
        msg = '<i><u>Warning:</u></i><p>'
        if rotate_a_axis:
            msg += "Using 4th axis rotation while all Work Coordinate Systems isn't aligned properly may result in unexpected results, including damage to property and person.<p>"
        else:
            msg += "Some Work Coordinate Systems aren't aligned properly which may result in unexpected results, including damage to property and person.<p>"
        msg += "Do NOT use the result from this plug-in unless you have personally verified that the result can be used.<p>"
        res = ui.messageBox(msg,
                            "WARNING! Do not proceed!",
                            adsk.core.MessageBoxButtonTypes.OKCancelButtonType,
                            adsk.core.MessageBoxIconTypes.CriticalIconType)
        if res != adsk.core.DialogResults.DialogOK:
            Utils.log('PostRunner: User cancelled operation due to unaligned WCS.')
            return False

    needAAxisRotation, setups = Setups.AAxisRotationRequired()
    if should_warn_machine_lacks_a_axis(
        has_machine=Programs.Current.hasMachine,
        machine_has_a_axis=Programs.Current.machineHasAAxis,
        a_axis_rotation_required=needAAxisRotation,
    ):
        Utils.log(f'PostRunner: Machine {Programs.Current.machineName} does not support A axis but setups {setups} require A axis rotation.', adsk.core.LogLevels.WarningLogLevel)
        msg = '<i><u>Warning:</u></i><p>'
        msg += f"The selected machine '{Programs.Current.machineName}' does not support A axis rotation, but the following setups require A axis rotation:<p>"
        for setupName, angle in setups:
            msg += f"{setupName} ({angle}°)<p>"
        msg += "Using 4th axis rotation while the machine doesn't support it may result in unexpected results, including damage to property and person.<p>"
        msg += "Do NOT use the result from this plug-in unless you have personally verified that the result can be used.<p>"
        res = ui.messageBox(msg,
                            "WARNING! Do not proceed!",
                            adsk.core.MessageBoxButtonTypes.OKCancelButtonType,
                            adsk.core.MessageBoxIconTypes.CriticalIconType)
        if res != adsk.core.DialogResults.DialogOK:
            Utils.log('PostRunner: User cancelled operation due to unsupported A axis rotation.')
            return False
    return True


def confirm_rotated_setups_without_a_axis(ui, rotate_a_axis: bool) -> bool:
    """
    The dialog warns about this when the A-axis checkbox is toggled off.
    Without the dialog, warn before merging rotated setups into one file.
    """
    needsRotation, rotatedSetups = Setups.AAxisRotationRequired()
    if not needsRotation or rotate_a_axis:
        return True
    listing = ''.join(Strings("<li>{name}: {degrees}°</li>").format(name=name, degrees=degrees)
                      for name, degrees in rotatedSetups)
    msg = Strings("These setups are rotated relative to the first selected setup. Without A-axis rotation, combining them into one file may produce unexpected motion.<p>Rotated setups:<ul>{rotatedSetups}</ul><p>Do you want to continue?").format(rotatedSetups=listing)
    res = ui.messageBox(msg, config.CMD_NAME,
                        adsk.core.MessageBoxButtonTypes.OKCancelButtonType,
                        adsk.core.MessageBoxIconTypes.WarningIconType)
    return res == adsk.core.DialogResults.DialogOK


def single_file_target() -> Optional[Path]:
    """The combined file that will be written, when grouping is Single file."""
    if Settings(Settings.OPERATIONS_GROUPING) != Settings.OperationsGroupings.SINGLE_FILE:
        return None
    program = Programs.Current
    return combined_output_path(program.GetOutputFolder(), program.fileName, program.fileExtension)


def ask_overwrite(ui, detail: str) -> bool:
    msg = detail + "<p>" + Strings("Overwrite it?")
    res = ui.messageBox(msg, config.CMD_NAME,
                        adsk.core.MessageBoxButtonTypes.YesNoButtonType,
                        adsk.core.MessageBoxIconTypes.QuestionIconType)
    return res == adsk.core.DialogResults.DialogYes


def run_post() -> list[Path]:
    """Post every selected setup and write the output files."""
    run_report.reset()
    with tempfile.TemporaryDirectory() as tmpdir:
        Programs.Current.Process(Path(tmpdir))
        Programs.Current.Generate()
    return run_report.written()


def run_with_overwrite_prompt(ui) -> Optional[list[Path]]:
    """
    Run the post, asking before overwriting instead of failing.

    For Single file output the target is checked up front, so the user is
    asked before any time is spent posting. Other groupings write several
    files whose names are only known while writing; there a clash is
    caught and, after a Yes, the post is run again with overwrite on.

    Returns the written files, or None if the user declined to overwrite.
    """
    previous = Settings(Settings.OVERWRITE_FILES)
    allow = bool(previous)
    try:
        if not allow:
            target = single_file_target()
            if target is not None and target.exists():
                if not ask_overwrite(ui, Strings("{path} already exists.").format(path=str(target))):
                    return None
                allow = True
                Settings.Set(Settings.OVERWRITE_FILES, True)
        try:
            return run_post()
        except FileExistsError as exc:
            if allow:
                raise
            if not ask_overwrite(ui, str(exc)):
                return None
            Settings.Set(Settings.OVERWRITE_FILES, True)
            return run_post()
    finally:
        Settings.Set(Settings.OVERWRITE_FILES, previous)


def report_success(ui, outputs: list[Path]) -> None:
    """Tell the user what was written and offer to open the folder."""
    from . import auto_program
    auto_program.remember(Programs.Current)  # so new documents can get an NC Program automatically
    folder = common_folder(outputs) or Programs.Current.GetOutputFolder()
    if outputs:
        msg = Strings("Wrote {count} file(s) to:<br>{folder}<p>{files}<p>Open the folder?").format(
            count=len(outputs), folder=str(folder), files=describe_outputs(outputs))
    else:
        msg = Strings("Posting finished. Output folder:<br>{folder}<p>Open the folder?").format(folder=str(folder))
    res = ui.messageBox(msg, config.CMD_NAME,
                        adsk.core.MessageBoxButtonTypes.YesNoButtonType,
                        adsk.core.MessageBoxIconTypes.InformationIconType)
    if res == adsk.core.DialogResults.DialogYes:
        if not open_in_file_browser(folder):
            Utils.log(f'PostRunner: could not open folder {folder}', adsk.core.LogLevels.WarningLogLevel)
