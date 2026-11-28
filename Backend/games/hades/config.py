"""Read-only install, Steam manifest, and Mach-O identity discovery for Hades."""

import json
import os
from pathlib import Path
import platform
import plistlib
import struct
import sys
from typing import Any, Optional
from xml.parsers.expat import ExpatError

from core.module_manifest import GameModuleManifest
from core.target_probe import bounded_run
from .mailbox import DEFAULT_TRANSPORT_MODE
from .operation_budgets import LLDB_MODULE_PATH_TIMEOUT_SECONDS

MODULE_DIR = Path(__file__).resolve().parent
MODULE_MANIFEST = GameModuleManifest.load(MODULE_DIR / 'module.json')
_RAW_MODULE = json.loads((MODULE_DIR / 'module.json').read_text(encoding='utf-8'))

STEAM_APP_ID = MODULE_MANIFEST.steam_app_id
SUPPORTED_BUILD = dict(_RAW_MODULE['supportedBuild'])
DISPLAY_NAME = MODULE_MANIFEST.display_name
PROCESS_NAME = MODULE_MANIFEST.process_name
BUNDLE_IDENTIFIER = MODULE_MANIFEST.bundle_identifier
EXECUTABLE_SUFFIX = MODULE_MANIFEST.executable_path_suffix or 'Hades/Game.macOS.app/Contents/MacOS/Game.macOS'
GAME_APP_DIRNAME = 'Hades'
GAME_APP_NAME = 'Game.macOS.app'
GAME_EXECUTABLE_NAME = PROCESS_NAME
GAME_ARCHITECTURE = str(SUPPORTED_BUILD.get('architecture', 'x86_64'))

_FAT_MAGIC = 0xCAFEBABE
_MH_MAGIC_64 = 0xFEEDFACF
_CPU_TYPE_X86_64 = 0x01000007
_LC_UUID = 0x1B

HOME = Path.home()
_INITIAL_HOME = HOME


def _effective_home(home: Optional[Path] = None) -> Path:
    if home is not None:
        return Path(home)
    if HOME != _INITIAL_HOME:
        return HOME
    return Path.home()


def saves_dir(home: Optional[Path] = None) -> Path:
    """Resolve the primary save directory declared in module.json."""
    roots = (_RAW_MODULE.get('saveManagement') or {}).get('roots') or ()
    raw = roots[0].get('path') if roots and isinstance(roots[0], dict) else None
    if isinstance(raw, str) and raw.startswith('~/'):
        return _effective_home(home) / raw[2:]
    if isinstance(raw, str) and raw:
        return Path(raw)
    return _effective_home(home) / 'Library/Application Support/Supergiant Games/Hades'


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

    prioritized = [item for item in candidates if STEAM_APP_ID and STEAM_APP_ID in item[1]]
    others = [item for item in candidates if not STEAM_APP_ID or STEAM_APP_ID not in item[1]]
    ordered: list[tuple[Path, set[str]]] = []
    seen: set[Path] = set()
    for lib_root, apps in [*prioritized, *others, (default_root, set())]:
        if lib_root not in seen:
            seen.add(lib_root)
            ordered.append((lib_root, apps))
    return ordered


def _steamapps_candidates(lib_root: Path) -> tuple[Path, ...]:
    return (lib_root / 'steamapps', lib_root / 'SteamApps')


def _read_acf(manifest_path: Path) -> dict[str, Any]:
    if not manifest_path.is_file():
        return {}
    try:
        parsed = parse_vdf(manifest_path.read_text(encoding='utf-8', errors='replace'))
    except OSError:
        return {}
    app_state = parsed.get('appstate')
    return app_state if isinstance(app_state, dict) else parsed


def _is_complete_game_bundle(candidate: Path) -> bool:
    if candidate.is_symlink() or not candidate.is_dir():
        return False
    executable = candidate / 'Contents' / 'MacOS' / GAME_EXECUTABLE_NAME
    if executable.is_symlink() or not executable.is_file():
        return False
    info_path = candidate / 'Contents' / 'Info.plist'
    if info_path.is_symlink() or not info_path.is_file():
        return False
    try:
        with info_path.open('rb') as stream:
            info = plistlib.load(stream)
    except (OSError, ValueError, plistlib.InvalidFileException, ExpatError):
        return False
    return isinstance(info, dict) and info.get('CFBundleExecutable') == GAME_EXECUTABLE_NAME


def _steam_manifest_for_bundle(bundle: Path, *, home: Path) -> Path:
    filename = f'appmanifest_{STEAM_APP_ID}.acf' if STEAM_APP_ID else ''
    if not filename:
        return home / 'Library/Application Support/Steam/steamapps' / 'appmanifest_unknown.acf'
    for ancestor in bundle.parents:
        direct = ancestor / filename
        if direct.is_file():
            return direct
    if bundle.parent.name == 'common':
        return bundle.parent.parent / filename
    if bundle.parent.parent.name == 'common':
        return bundle.parent.parent.parent / filename
    return home / 'Library/Application Support/Steam/steamapps' / filename


def resolve_game_install(
    located_executable: Optional[Path] = None,
    *,
    home: Optional[Path] = None,
) -> tuple[Path, Path, Path]:
    """Return `(game_app, game_executable, steam_manifest)` from live executable or Steam."""
    effective_home = _effective_home(home)
    if located_executable is not None:
        exe = Path(located_executable)
        if exe.parent.name == 'MacOS' and exe.parent.parent.name == 'Contents':
            bundle = exe.parent.parent.parent
            return bundle, exe, _steam_manifest_for_bundle(bundle, home=effective_home)

    filename = f'appmanifest_{STEAM_APP_ID}.acf' if STEAM_APP_ID else 'appmanifest.acf'
    first_acf: Optional[tuple[Path, Path, Path]] = None
    for lib_root, _ in _steam_library_entries(effective_home):
        for steamapps in _steamapps_candidates(lib_root):
            acf = steamapps / filename
            app_state = _read_acf(acf)
            raw_dir = app_state.get('installdir')
            install_dir = raw_dir.strip() if isinstance(raw_dir, str) and raw_dir.strip() else GAME_APP_DIRNAME
            for app_dir in dict.fromkeys((install_dir, GAME_APP_DIRNAME)):
                candidate = steamapps / 'common' / app_dir / GAME_APP_NAME
                exe = candidate / 'Contents' / 'MacOS' / GAME_EXECUTABLE_NAME
                if _is_complete_game_bundle(candidate):
                    return candidate, exe, acf
            if first_acf is None and acf.is_file():
                candidate = steamapps / 'common' / install_dir / GAME_APP_NAME
                first_acf = (candidate, candidate / 'Contents' / 'MacOS' / GAME_EXECUTABLE_NAME, acf)
    if first_acf is not None:
        return first_acf

    default_steamapps = effective_home / 'Library/Application Support/Steam/steamapps'
    default_app = default_steamapps / 'common' / GAME_APP_DIRNAME / GAME_APP_NAME
    return default_app, default_app / 'Contents' / 'MacOS' / GAME_EXECUTABLE_NAME, default_steamapps / filename


def _format_uuid(raw_bytes: bytes) -> str:
    hex_str = raw_bytes.hex().upper()
    return f'{hex_str[0:8]}-{hex_str[8:12]}-{hex_str[12:16]}-{hex_str[16:20]}-{hex_str[20:32]}'


def _macho64_slice_uuid(data: bytes, *, target_cputype: int = _CPU_TYPE_X86_64) -> str:
    if len(data) < 32:
        raise ValueError('Incomplete Mach-O slice')
    magic, cpu, _, _, count, size, _, _ = struct.unpack_from('<8I', data)
    if magic != _MH_MAGIC_64 or cpu != target_cputype or size > len(data) - 32:
        raise ValueError(f'Not a 64-bit Mach-O image for cputype 0x{target_cputype:x}')
    cursor, end = 32, 32 + size
    for _ in range(count):
        if cursor + 8 > end:
            break
        command, length = struct.unpack_from('<II', data, cursor)
        if length < 8 or cursor + length > end:
            break
        if command == _LC_UUID and length == 24:
            return _format_uuid(data[cursor + 8 : cursor + 24])
        cursor += length
    raise ValueError('Mach-O slice has no LC_UUID')


def executable_uuid(path: Path, *, target_cputype: int = _CPU_TYPE_X86_64) -> Optional[str]:
    """Return formatted `LC_UUID` for the target architecture slice, or None if unreadable."""
    try:
        data = Path(path).read_bytes()
    except OSError:
        return None
    if len(data) < 8:
        return None
    be_magic, nfat_arch = struct.unpack_from('>II', data)
    try:
        if be_magic == _FAT_MAGIC:
            if nfat_arch == 0 or nfat_arch > 16 or 8 + nfat_arch * 20 > len(data):
                return None
            for index in range(nfat_arch):
                cputype, _, offset, size, _ = struct.unpack_from('>5I', data, 8 + index * 20)
                if cputype == target_cputype:
                    if size < 32 or offset > len(data) or size > len(data) - offset:
                        return None
                    return _macho64_slice_uuid(data[offset : offset + size], target_cputype=target_cputype)
            return None
        return _macho64_slice_uuid(data, target_cputype=target_cputype)
    except ValueError:
        return None


def read_build_version(game_app: Path) -> str:
    buildinfo = game_app / 'Contents' / 'Resources' / 'Content' / 'buildinfo.txt'
    try:
        for line in buildinfo.read_text(encoding='utf-8', errors='replace').splitlines():
            stripped = line.strip()
            if stripped:
                return stripped
    except OSError:
        pass
    return ''


def inspect_install(
    located_executable: Optional[Path] = None,
    *,
    home: Optional[Path] = None,
) -> dict[str, Any]:
    """Inspect Hades bundle installation and supportedBuild compatibility without attaching."""
    game_app, executable, manifest_path = resolve_game_install(located_executable, home=home)
    installed = game_app.is_dir() and executable.is_file()
    version = read_build_version(game_app) if installed else ''
    acf = _read_acf(manifest_path)
    steam_build = str(acf.get('buildid') or '') if isinstance(acf, dict) else ''
    image_uuid = executable_uuid(executable) if installed else None

    expected_version = str(SUPPORTED_BUILD.get('contentBuildInfo', ''))
    expected_uuid = str(SUPPORTED_BUILD.get('uuid', '')).upper()
    expected_steam_build = str(SUPPORTED_BUILD.get('steamBuildID', ''))

    warnings: list[str] = []
    if not installed:
        warnings.append('not_installed')
    else:
        if expected_version and version != expected_version:
            warnings.append(f'contentBuildInfo {version or "?"} != {expected_version}')
        if expected_uuid and image_uuid != expected_uuid:
            warnings.append(f'uuid {image_uuid or "?"} != {expected_uuid}')
        if steam_build and expected_steam_build and steam_build != expected_steam_build:
            warnings.append(f'steamBuildID {steam_build} != {expected_steam_build}')

    compatible = (
        installed
        and (not expected_version or version == expected_version)
        and (not expected_uuid or image_uuid == expected_uuid)
        and (not steam_build or not expected_steam_build or steam_build == expected_steam_build)
    )
    return {
        'gameApp': game_app,
        'executable': executable,
        'manifestPath': manifest_path,
        'installed': installed,
        'version': version,
        'steamBuild': steam_build,
        'uuid': image_uuid,
        'compatible': compatible,
        'warnings': warnings,
    }


def installed_version(located_executable: Optional[Path] = None, *, home: Optional[Path] = None) -> str:
    return inspect_install(located_executable, home=home)['version']


def is_installed(home: Optional[Path] = None) -> bool:
    return bool(inspect_install(home=home)['installed'])


def is_compatible_executable(executable: Path) -> bool:
    return bool(inspect_install(executable)['compatible'])


def probe_lldb() -> tuple[bool, str]:
    try:
        result = bounded_run(['/usr/bin/xcrun', '--find', 'lldb'], LLDB_MODULE_PATH_TIMEOUT_SECONDS, text=True)
        return result.returncode == 0, (result.stdout.strip() or result.stderr.strip())
    except Exception as error:
        return False, str(error)


def probe_lldb_python() -> tuple[bool, str]:
    probe = (
        'import subprocess,sys; p=subprocess.check_output(["/usr/bin/xcrun","lldb","-P"], text=True).strip(); '
        'sys.path.insert(0,p); import lldb; print(lldb.SBDebugger)'
    )
    try:
        result = bounded_run(['/usr/bin/xcrun', 'python3', '-c', probe], LLDB_MODULE_PATH_TIMEOUT_SECONDS, text=True)
        return result.returncode == 0, (result.stdout.strip() or result.stderr.strip())
    except Exception as error:
        return False, str(error)


def probe_rosetta() -> tuple[bool, str]:
    machine = platform.machine().lower()
    if machine == 'x86_64':
        return True, 'x86_64'
    if sys.platform != 'darwin':
        return False, platform.platform()
    rosetta_runtime = Path('/Library/Apple/usr/libexec/oah/libRosettaRuntime')
    if rosetta_runtime.exists():
        return True, str(rosetta_runtime)
    return bool(os.path.exists('/Library/Apple/usr/share/rosetta/rosetta')), 'Rosetta 2'


def probe_native_mailbox() -> tuple[bool, str, str]:
    """Return `(ok, mode, detail)` for the native x86_64/arm64 command mailbox library."""
    from . import native_mailbox

    mode = os.environ.get('MGT_HADES_TRANSPORT', DEFAULT_TRANSPORT_MODE)
    dylib = MODULE_DIR / 'native' / 'libMGTHadesCommandMailbox.dylib'
    if not dylib.is_file():
        return False, mode, str(dylib)
    try:
        uuid_hex = native_mailbox.slice_uuid(dylib, target_cputype=native_mailbox.CPU_TYPE_X86_64)
        return True, mode, f'{mode} · {uuid_hex}'
    except ValueError as error:
        return False, mode, str(error)
