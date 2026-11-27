# Assuming you have not changed the general structure of the template no modification is needed in this file.
from __future__ import annotations
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))


def _forget_modules():
    """Drop this add-in's other modules from Python's cache.

    Fusion keeps one Python process for the whole session, so after an update a
    Stop/Run in Scripts and Add-Ins would otherwise keep running the old submodules.
    Matches by file location, so it works however Fusion names the package.
    """
    me = os.path.abspath(__file__)
    parts = __name__.split('.')
    keep = {'.'.join(parts[:i]) for i in range(1, len(parts) + 1)}   # this module and its package
    drop = []
    for name, mod in list(sys.modules.items()):
        if name in keep:
            continue
        try:
            f = getattr(mod, '__file__', None)
            # folders without __init__.py (namespace packages) have no __file__, only __path__
            places = [f] if f else list(getattr(mod, '__path__', None) or [])
        except Exception:
            continue
        if any(os.path.abspath(p) != me and os.path.abspath(p).startswith(_HERE + os.sep) for p in places):
            drop.append(name)
    for name in drop:                    # decide first: a namespace path looks up its parent
        sys.modules.pop(name, None)


_forget_modules()

from .lib.fusionAddInUtils import Events  # noqa: E402
from .lib.fusionAddInUtils import Utils  # noqa: E402
from .commands.commands import Commands  # noqa: E402


def run(context):
    try:
        Utils.log("PostProcessorUtil run")

        # This will run the start function in each of your commands as defined in commands/__init__.py
        Commands.start()

    except:
        Utils.handleError('run')


def stop(context):
    try:
        # Remove all of the event handlers your app has created
        Events.clear()

        # This will run the start function in each of your commands as defined in commands/__init__.py
        Commands.stop()

    except:
        Utils.handleError('stop')
    _forget_modules()
