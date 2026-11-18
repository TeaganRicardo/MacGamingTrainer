import json
from pathlib import Path

from core.module_manifest import GameModuleManifest

MODULE_DIR = Path(__file__).resolve().parent
MODULE_MANIFEST = GameModuleManifest.load(MODULE_DIR / 'module.json')

# Resident Lua source is trusted Trainer-owned code and is substantially larger
# than a normal dispatch. Keep its input budget bounded, but separate it from
# the response buffer budget so runtime growth does not silently consume output
# headroom or fail before luaL_loadbufferx sees a valid bootstrap.
LUA_TRANSPORT_SOURCE_LIMIT_BYTES = 1_048_576
LUA_TRANSPORT_RESULT_LIMIT_BYTES = 262_144

# Game-owned safety budget for one LLDB sidecar request/reply. Host command
# deadlines are separate and may be shorter or longer; Core owns only the
# generic timeout mechanism, not this debugger/runtime policy.
LLDB_SIDECAR_REPLY_TIMEOUT_SECONDS = 30.0

HOME = Path.home()
STEAMAPPS = HOME / 'Library/Application Support/Steam/steamapps'
_RAW_MODULE = json.loads((MODULE_DIR / 'module.json').read_text(encoding='utf-8'))
STEAM_APP_ID = _RAW_MODULE.get('steamAppId')
SUPPORTED_BUILD = _RAW_MODULE['supportedBuild']
if not isinstance(STEAM_APP_ID, str) or not STEAM_APP_ID.isdigit():
    raise RuntimeError('Hades II module manifest is missing a valid steamAppId.')
# Target identity is owned by module.json; the install, save and Steam
# locations below are this module's macOS projection of it.
DISPLAY_NAME = MODULE_MANIFEST.display_name
PROCESS_NAME = MODULE_MANIFEST.process_name
BUNDLE_IDENTIFIER = MODULE_MANIFEST.bundle_identifier
GAME_APP = STEAMAPPS / 'common/Hades II/Hades II.app'
GAME_EXECUTABLE_NAME = 'Hades II'
GAME_EXECUTABLE = GAME_APP / 'Contents' / 'MacOS' / GAME_EXECUTABLE_NAME
GAME_SAVES = HOME / 'Library/Application Support/Supergiant Games/Hades II'
GAME_ARCHITECTURE = 'arm64'
STEAM_MANIFEST = STEAMAPPS / f'appmanifest_{STEAM_APP_ID}.acf'
STEAM_LAUNCH_URL = f'steam://rungameid/{STEAM_APP_ID}'

# Preserve the existing Hades II data location. New game modules should use a
# namespaced directory under MacGamingTrainer/<game-id> unless migration requires otherwise.
DATA = HOME / 'Library/Application Support/MacGamingTrainer'


def supported_reference_path(name: str, module_file: Path = Path(__file__)) -> Path:
    """Locate a supported-build reference file declared as a packaged app resource.

    Only `@supportedBuild/<name>` appResources reach the packaged app, at their
    declared destination; development execution reads the module-declared
    reference directory. An undeclared file is never read in either mode.
    """
    destinations = [item.get('destination') for item in _RAW_MODULE.get('appResources', ())
                    if isinstance(item, dict) and item.get('source') == '@supportedBuild/' + name]
    if len(destinations) != 1 or not isinstance(destinations[0], str):
        raise LookupError(f'Hades II reference file {name!r} is not a declared supportedBuild app resource.')
    resource_root = Path(module_file).resolve().parents[3]
    if resource_root.name == 'Resources' and resource_root.parent.name == 'Contents':
        return resource_root / destinations[0]
    return resource_root / SUPPORTED_BUILD['referenceDirectory'] / name
