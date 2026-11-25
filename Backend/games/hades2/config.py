import json
from pathlib import Path
from typing import Any, Optional

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
_INITIAL_HOME = HOME
STEAMAPPS = HOME / 'Library/Application Support/Steam/steamapps'
_RAW_MODULE = json.loads((MODULE_DIR / 'module.json').read_text(encoding='utf-8'))
STEAM_APP_ID = MODULE_MANIFEST.steam_app_id
SUPPORTED_BUILD = _RAW_MODULE['supportedBuild']
if STEAM_APP_ID is None:
    raise RuntimeError('Hades II module manifest is missing a valid steamAppId.')
# Target identity is owned by module.json; the install, save and Steam
# locations below are this module's macOS fallback projection of it.
DISPLAY_NAME = MODULE_MANIFEST.display_name
PROCESS_NAME = MODULE_MANIFEST.process_name
BUNDLE_IDENTIFIER = MODULE_MANIFEST.bundle_identifier
GAME_APP_DIRNAME = 'Hades II'
GAME_APP_NAME = 'Hades II.app'
GAME_APP = STEAMAPPS / 'common' / GAME_APP_DIRNAME / GAME_APP_NAME
GAME_EXECUTABLE_NAME = 'Hades II'
GAME_EXECUTABLE = GAME_APP / 'Contents' / 'MacOS' / GAME_EXECUTABLE_NAME
GAME_SAVES = HOME / 'Library/Application Support/Supergiant Games/Hades II'
GAME_ARCHITECTURE = SUPPORTED_BUILD['architecture']
STEAM_MANIFEST = STEAMAPPS / f'appmanifest_{STEAM_APP_ID}.acf'


def _effective_home(home: Optional[Path] = None) -> Path:
    if home is not None:
        return Path(home)
    if HOME != _INITIAL_HOME:
        return HOME
    return Path.home()


def _tokenize_vdf(text: str) -> list[str]:
    tokens: list[str] = []
    index = 0
    length = len(text)
    while index < length:
        ch = text[index]
        if ch.isspace():
            index += 1
        elif ch == '/' and index + 1 < length and text[index + 1] == '/':
            newline = text.find('\n', index + 2)
            index = length if newline < 0 else newline + 1
        elif ch in ('{', '}'):
            tokens.append(ch)
            index += 1
        elif ch == '"':
            index += 1
            chars: list[str] = []
            while index < length:
                current = text[index]
                if current == '\\' and index + 1 < length:
                    nxt = text[index + 1]
                    chars.append({'n': '\n', 't': '\t', 'r': '\r'}.get(nxt, nxt))
                    index += 2
                    continue
                if current == '"':
                    index += 1
                    break
                chars.append(current)
                index += 1
            tokens.append(''.join(chars))
        else:
            start = index
            while index < length and not text[index].isspace() and text[index] not in ('{', '}', '"'):
                index += 1
            tokens.append(text[start:index])
    return tokens


def _parse_vdf_mapping(tokens: list[str], index: int = 0) -> tuple[dict[str, Any], int]:
    result: dict[str, Any] = {}
    length = len(tokens)
    while index < length:
        token = tokens[index]
        if token == '}':
            return result, index + 1
        if token == '{':
            index += 1
            continue
        key = token
        index += 1
        if index >= length:
            break
        if tokens[index] == '{':
            child, index = _parse_vdf_mapping(tokens, index + 1)
            result[key.lower()] = child
        elif tokens[index] == '}':
            break
        else:
            result[key.lower()] = tokens[index]
            index += 1
    return result, index


def parse_vdf(text: str) -> dict[str, Any]:
    """Parse Valve KeyValues (`.vdf` / `.acf`) text into case-folded mappings."""
    mapping, _ = _parse_vdf_mapping(_tokenize_vdf(text))
    return mapping


def _steam_library_entries(home: Path) -> list[tuple[Path, set[str]]]:
    default_root = home / 'Library/Application Support/Steam'
    candidates: list[tuple[Path, set[str]]] = []
    for vdf_path in (default_root / 'steamapps/libraryfolders.vdf', default_root / 'config/libraryfolders.vdf'):
        if not vdf_path.is_file():
            continue
        try:
            parsed = parse_vdf(vdf_path.read_text(encoding='utf-8', errors='replace'))
        except OSError:
            continue
        section = parsed.get('libraryfolders') if isinstance(parsed.get('libraryfolders'), dict) else parsed
        if not isinstance(section, dict):
            continue
        for key, value in section.items():
            if isinstance(value, str) and value.strip() and key.isdigit():
                candidates.append((Path(value.strip()), set()))
            elif isinstance(value, dict):
                raw_path = value.get('path')
                if isinstance(raw_path, str) and raw_path.strip():
                    apps = value.get('apps')
                    app_ids = set(apps) if isinstance(apps, dict) else set()
                    candidates.append((Path(raw_path.strip()), app_ids))
        if candidates:
            break

    prioritized = [item for item in candidates if STEAM_APP_ID in item[1]]
    others = [item for item in candidates if STEAM_APP_ID not in item[1]]
    ordered: list[tuple[Path, set[str]]] = []
    seen: set[Path] = set()
    for lib_root, apps in [*prioritized, *others, (default_root, set())]:
        if lib_root not in seen:
            seen.add(lib_root)
            ordered.append((lib_root, apps))
    return ordered


def _steamapps_candidates(lib_root: Path) -> tuple[Path, ...]:
    return (lib_root / 'steamapps', lib_root / 'SteamApps')


def _acf_install_dir(manifest_path: Path) -> Optional[str]:
    if not manifest_path.is_file():
        return None
    try:
        parsed = parse_vdf(manifest_path.read_text(encoding='utf-8', errors='replace'))
    except OSError:
        return None
    app_state = parsed.get('appstate') if isinstance(parsed.get('appstate'), dict) else parsed
    if isinstance(app_state, dict):
        install_dir = app_state.get('installdir')
        if isinstance(install_dir, str) and install_dir.strip():
            return install_dir.strip()
    return None


def steam_manifest_for_bundle(
    bundle_path: Path,
    steam_app_id: Optional[str] = None,
    *,
    home: Optional[Path] = None,
) -> Path:
    """Resolve the Steam appmanifest matching `bundle_path`, falling back cleanly."""
    app_id = STEAM_APP_ID if steam_app_id is None else steam_app_id
    bundle = Path(bundle_path)
    filename = f'appmanifest_{app_id}.acf'
    for ancestor in bundle.parents:
        direct = ancestor / filename
        if direct.is_file():
            return direct
    if bundle.parent.name == 'common':
        return bundle.parent.parent / filename
    if bundle.parent.parent.name == 'common':
        return bundle.parent.parent.parent / filename
    effective_home = _effective_home(home)
    for lib_root, _ in _steam_library_entries(effective_home):
        for steamapps in _steamapps_candidates(lib_root):
            acf = steamapps / filename
            if acf.is_file():
                install_dir = _acf_install_dir(acf) or GAME_APP_DIRNAME
                if (steamapps / 'common' / install_dir / GAME_APP_NAME).resolve() == bundle.resolve():
                    return acf
    return effective_home / 'Library/Application Support/Steam/steamapps' / filename


def resolve_game_install(
    located_bundle: Optional[Path] = None,
    *,
    home: Optional[Path] = None,
) -> tuple[Path, Path, Path]:
    """Return `(game_app, game_executable, steam_manifest)` from live bundle or Steam libraries."""
    effective_home = _effective_home(home)
    if located_bundle is not None:
        bundle = Path(located_bundle)
        return (
            bundle,
            bundle / 'Contents' / 'MacOS' / GAME_EXECUTABLE_NAME,
            steam_manifest_for_bundle(bundle, home=effective_home),
        )

    filename = f'appmanifest_{STEAM_APP_ID}.acf'
    first_acf: Optional[tuple[Path, Path, Path]] = None
    for lib_root, _ in _steam_library_entries(effective_home):
        for steamapps in _steamapps_candidates(lib_root):
            acf = steamapps / filename
            install_dir = _acf_install_dir(acf) or GAME_APP_DIRNAME
            for app_dir in dict.fromkeys((install_dir, GAME_APP_DIRNAME)):
                candidate = steamapps / 'common' / app_dir / GAME_APP_NAME
                exe = candidate / 'Contents' / 'MacOS' / GAME_EXECUTABLE_NAME
                if candidate.exists():
                    return candidate, exe, acf
            if first_acf is None and acf.is_file():
                candidate = steamapps / 'common' / install_dir / GAME_APP_NAME
                first_acf = (candidate, candidate / 'Contents' / 'MacOS' / GAME_EXECUTABLE_NAME, acf)
    if first_acf is not None:
        return first_acf

    default_steamapps = effective_home / 'Library/Application Support/Steam/steamapps'
    default_app = default_steamapps / 'common' / GAME_APP_DIRNAME / GAME_APP_NAME
    return (
        default_app,
        default_app / 'Contents' / 'MacOS' / GAME_EXECUTABLE_NAME,
        default_steamapps / filename,
    )


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
        return resource_root / 'Modules' / MODULE_MANIFEST.id / destinations[0]
    return resource_root / SUPPORTED_BUILD['referenceDirectory'] / name
