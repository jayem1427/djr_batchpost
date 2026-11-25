import json
from pathlib import Path


from .. import config
from ..attributes import Attributes
from ..const import *
from ....config import PLUGIN_VERSION as GLOBAL_PLUGIN_VERSION
from ....lib.fusionAddInUtils.general_utils import *

from .constants import Constants

_UNSET = object()

class _SettingsMeta(type):
    
    def __iter__(cls):
        return iter(cls._items)
    
    def __call__(cls, key, /, value = _UNSET):
        if value is _UNSET:
            return cls.Get(key)
        cls.Set(key, value)
        return cls.Get(key)

class Settings(Constants, metaclass=_SettingsMeta):
    """Manages the user settings for the Post Processor Add-In."""

    _default = None
    _path = None
    _fMustSave = False
    _inputs = None
    _items = {}

    #region Initial default values of settings
    # See above definitions for details
    _defaultSettings = {
        Constants.END_CODES:                    "M5\nM9\nM30",
        Constants.OVERWRITE_FILES:              False,
        Constants.CLEAR_FOLDER:                 False,
        Constants.OUTPUT_FOLDER:                "",
        Constants.FILE_SEQUENCE:                False,
        Constants.NUMERIC_NAME:                 False,  
        Constants.FILE_SEQUENCE_DIGITS:         1,
        Constants.SHOW_LINE_SEQUENCING:         False,
        Constants.LINE_SEQUENCE:                False,
        Constants.LINE_SEQUENCE_DIGITS:         2,
        Constants.LINE_SEQUENCE_INTERVAL:       5,
        Constants.OPERATIONS_GROUPING:          Constants.OperationsGroupings.SINGLE_FILE,
        Constants.COMBINE_TOOL:                 False,
        Constants.VERSION:                      config.SETTINGS_VERSION,
        Constants.PLUGIN_VERSION:               GLOBAL_PLUGIN_VERSION,
        Constants.NC_PROGRAM:                   "",
        Constants.LANGUAGE:                     "en",
        Constants.TOOL_CHANGE:                  "M9",
        Constants.RESTORE_RAPID_MOVES:          False,
        Constants.RAPID_MOVES_MINIMUM_DISTANCE: 20,
        Constants.INITIAL_DELAY:                0.2,
        Constants.POST_RETRIES:                 3,
        Constants.ROTATE_A_AXIS:                False,
        Constants.SAFE_Y_RETRACTION:            True,
        Constants.Y_RETRACTION_COORDINATE:      -100,
        Constants.FLAT_FILE_STRUCTURE:          False,
        Constants.USE_REGEX:                    False,
        Constants.FIND_STRING:                  "",
        Constants.REPLACE_STRING:               "",
        Constants.REPLACE_ONLY_SELECTED:        True,
        Constants.HEADER_END_CODES:             "G20\nG21",
    }
    #endregion

    @classmethod
    def Load(cls, attr: Attributes = None):
        documentItems = None
        if attr and attr.count > 0:
            try:
                documentItems = json.loads(attr.itemByName(Const.ATTR_GROUP, Const.ATTR_NAME).value)
                if documentItems.get(Constants.VERSION) is not None and documentItems[Constants.VERSION] == config.SETTINGS_VERSION:
                    # Still merge newly-added keys so older documents that
                    # already have this version number pick up defaults.
                    cls._items = documentItems
                    cls.Update(Settings._defaultSettings, cls._items)
                    return  # settings are valid for this version
            except Exception:
                documentItems = None
            
        # Document does not have valid settings, get defaults
        if not cls._default:
            # Haven't read the settings file yet
            file = None
            path = cls._getPath()
            if path.exists() and path.is_file():
                    with open(path) as file:
                        cls._default = json.load(file)
                    if cls._default[Constants.VERSION] != config.SETTINGS_VERSION:
                        cls.Update(Settings._defaultSettings, cls._default)
            else:
                cls._default = dict(Settings._defaultSettings)
                cls._fMustSave = True
        
        if documentItems:
            # Settings from an older settings version: keep the document's
            # values and add any keys introduced since.
            cls._items = documentItems
            cls.Update(cls._default, cls._items)
        else:
            # This document has no settings yet: start from the defaults,
            # not from whichever document was used last in this session.
            cls._items = dict(cls._default)

    @classmethod
    def SaveDefault(cls):
        cls._fMustSave = False
        cls._default = dict(cls._items)
        try:
            strSettings = json.dumps(cls._items, indent=4, sort_keys=True)
            file = open(cls._getPath(), "w")
            file.write(strSettings)
            file.close()
        except Exception:
            pass

    @classmethod
    def Defaults(cls) -> dict:
        """The defaults for new documents (read from the file if needed)."""
        if not cls._default:
            path = cls._getPath()
            try:
                with open(path) as file:
                    cls._default = json.load(file)
                cls.Update(Settings._defaultSettings, cls._default)
            except Exception:
                cls._default = dict(Settings._defaultSettings)
        return dict(cls._default)

    @classmethod
    def UpdateDefaults(cls, changes: dict) -> None:
        """Change some defaults for new documents and write the file. The
        open document's own settings are left alone."""
        defaults = cls.Defaults()
        defaults.update(changes)
        cls._default = defaults
        try:
            with open(cls._getPath(), "w") as file:
                file.write(json.dumps(defaults, indent=4, sort_keys=True))
        except Exception:
            pass

    @classmethod
    def Save(cls, attr: Attributes):
        if cls._fMustSave:
            cls.SaveDefault()
        attr.add(Const.ATTR_GROUP, Const.ATTR_NAME, json.dumps(cls._items))
            
    @classmethod
    def Update(cls, src, dst):
        for item in src:
            if not (item in dst):
                dst[item] = src[item]
        dst[Constants.VERSION] = src[Constants.VERSION]

    @classmethod
    def _getPath(cls) -> Path:
        if not cls._path:
            pos = __file__.rfind(".")
            if pos == -1:
                pos = len(__file__)
            cls._path = __file__[0:pos] + Const.SETTINGS_FILE_EXT
        return Path(cls._path)
    
    @classmethod
    def Get(cls, key):
        return cls._items.get(key, None)
    
    @classmethod
    def Set(cls, key, value):
        # Only the document copy changes here. The defaults file for new
        # documents is written by "Save as default settings" (SaveDefault),
        # or once on first run when no defaults file exists yet. Previously
        # every change also overwrote the defaults when the dialog closed,
        # which made the button meaningless and let per-run overrides leak.
        cls._items[key] = value