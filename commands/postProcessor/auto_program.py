"""
Creates an NC Program when a document doesn't have a usable one, using
the post processor remembered from your last successful post.
"""
from __future__ import annotations

from typing import Optional

import adsk.core
import adsk.cam

from . import post_memory
from .parameters import Parameters
from ...lib.fusionAddInUtils.general_utils import Utils

AUTO_PROGRAM_NAME = "DJR Batch Post"


def _post_library():
    return adsk.cam.CAMManager.get().libraryManager.postLibrary


def _location_urls(library, names):
    urls = []
    for name in names:
        location = getattr(adsk.cam.LibraryLocations, name, None)
        if location is None:
            continue
        try:
            urls.append(library.urlByLocation(location))
        except Exception:
            pass
    return urls


# Your own posts first, then Fusion's built-in library.
_USER_LOCATIONS = ("LocalLibraryLocation", "CloudLibraryLocation", "NetworkLibraryLocation")
_ALL_LOCATIONS = _USER_LOCATIONS + ("Fusion360LibraryLocation",)


def resolve_post() -> tuple[Optional[object], dict]:
    """(post configuration, remembered info). Post is None if none found."""
    info = post_memory.load()
    library = _post_library()
    if info:
        post = post_memory.find_post(library, _location_urls(library, _ALL_LOCATIONS), info)
        if post is not None:
            return post, info
        Utils.log(f"AutoProgram: remembered post '{info.get('description')}' not found in post libraries.",
                  adsk.core.LogLevels.WarningLogLevel)
        return None, info
    # Nothing remembered yet: fine if you only have one post of your own.
    return post_memory.only_post(library, _location_urls(library, _USER_LOCATIONS)), {}


def _set(params, name: str, value) -> None:
    param = params.itemByName(name)
    if param is not None and param.value is not None:
        param.value.value = value


def create_program(cam: adsk.cam.CAM, post, info: dict, file_name: str):
    """Add an NC Program covering every setup, with ``post`` attached."""
    ncInput = cam.ncPrograms.createInput()
    ncInput.displayName = AUTO_PROGRAM_NAME
    params = ncInput.parameters
    if info.get("outputFolder"):
        _set(params, Parameters.OUTPUT_FOLDER, info["outputFolder"])
    if file_name:
        _set(params, Parameters.FILE_NAME, file_name)
    _set(params, Parameters.OPEN_IN_EDITOR, False)
    ncInput.operations = [setup for setup in cam.setups if not setup.isSuppressed]
    program = cam.ncPrograms.add(ncInput)
    program.postConfiguration = post
    return program


def remember(program) -> None:
    """Remember the post + output folder of a program that just posted."""
    try:
        post = program._program.postConfiguration
        if post is not None:
            post_memory.save(post_memory.describe_post(post, program.GetOutputFolder()))
    except Exception:
        Utils.log("AutoProgram: could not remember post.", adsk.core.LogLevels.WarningLogLevel)
