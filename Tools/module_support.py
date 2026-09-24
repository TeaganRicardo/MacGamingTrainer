import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / 'Backend'
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from core.module_manifest import GameModuleManifest, ManifestError
from core.protocol import HOST_PROTOCOL_VERSION

_SWIFT_TYPE_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')
_BUNDLE_ID_RE = re.compile(r'^[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$')
_MACOS_VERSION_RE = re.compile(r'^[0-9]{1,2}(?:\.[0-9]{1,2}){1,2}$')
_SUPPORTED_SWIFT_ARCHES = frozenset({'arm64', 'x86_64'})


@dataclass(frozen=True)
class FrontendBuildSpec:
    source_directory: str
    module_type: str
    architectures: tuple
    minimum_macos: str


@dataclass(frozen=True)
class AppBuildSpec:
    bundle_identifier: str
    display_name: str


@dataclass(frozen=True)
class BuildRequirements:
    lldb_python: bool
    debugger_entitlement: bool
    entitlements: str


@dataclass(frozen=True)
class BuildManifest:
    runtime: GameModuleManifest
    frontend: FrontendBuildSpec
    app: AppBuildSpec
    requirements: BuildRequirements
    raw: dict

    @property
    def id(self): return self.runtime.id
    @property
    def display_name(self): return self.runtime.display_name
    @property
    def module_protocol_version(self): return self.runtime.module_protocol_version


def manifest_path(game_id: str) -> Path:
    return ROOT / 'Backend' / 'games' / game_id / 'module.json'


def _safe_relative_path(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ManifestError(f'{field} must be a non-empty relative path.')
    path = Path(value)
    if path.is_absolute() or '..' in path.parts:
        raise ManifestError(f'{field} must stay inside the project root.')
    return value


def _default_app_name(display_name, game_id):
    safe = ''.join('-' if ch in '/:' or ord(ch) < 32 else ch for ch in display_name).strip()
    return 'Mac Gaming Trainer - ' + (safe[:80].strip() or game_id)


def load_manifest(game_id: str) -> BuildManifest:
    path = manifest_path(game_id)
    runtime = GameModuleManifest.load(path)
    runtime.validate_backend_layout(ROOT / 'Backend')
    raw = json.loads(path.read_text(encoding='utf-8'))

    frontend = raw.get('frontend')
    if not isinstance(frontend, dict):
        raise ManifestError('frontend must be an object.')
    source_directory = _safe_relative_path(frontend.get('sourceDirectory'), 'frontend.sourceDirectory')
    module_type = frontend.get('moduleType')
    if not isinstance(module_type, str) or not _SWIFT_TYPE_RE.fullmatch(module_type):
        raise ManifestError('frontend.moduleType must be a Swift type identifier.')
    arches = frontend.get('architectures', [])
    if not isinstance(arches, list) or any(item not in _SUPPORTED_SWIFT_ARCHES for item in arches):
        raise ManifestError('frontend.architectures may contain only arm64/x86_64.')
    if len(set(arches)) != len(arches):
        raise ManifestError('frontend.architectures contains duplicates.')
    minimum_macos = frontend.get('minimumMacOS', '14.0')
    if not isinstance(minimum_macos, str) or not _MACOS_VERSION_RE.fullmatch(minimum_macos):
        raise ManifestError('frontend.minimumMacOS must look like 14.0 or 14.4.1.')
    frontend_spec = FrontendBuildSpec(source_directory, module_type, tuple(arches), minimum_macos)

    app = raw.get('app', {})
    if not isinstance(app, dict):
        raise ManifestError('app must be an object.')
    default_bundle = f"com.gao.macgamingtrainer.{runtime.id.replace('_', '-')}"
    bundle_identifier = app.get('bundleIdentifier', default_bundle)
    if not isinstance(bundle_identifier, str) or not _BUNDLE_ID_RE.fullmatch(bundle_identifier):
        raise ManifestError('app.bundleIdentifier must be a reverse-DNS identifier.')
    display_name = app.get('displayName', _default_app_name(runtime.display_name, runtime.id))
    if not isinstance(display_name, str) or not display_name.strip() or '/' in display_name or ':' in display_name:
        raise ManifestError('app.displayName must be a safe non-empty app name.')
    app_spec = AppBuildSpec(bundle_identifier, display_name.strip())

    req = raw.get('buildRequirements', {})
    if not isinstance(req, dict):
        raise ManifestError('buildRequirements must be an object.')
    lldb_python = req.get('lldbPython', False)
    debugger_entitlement = req.get('debuggerEntitlement', False)
    if type(lldb_python) is not bool or type(debugger_entitlement) is not bool:
        raise ManifestError('build requirement flags must be boolean.')
    entitlements = req.get('entitlements', '')
    if entitlements:
        entitlements = _safe_relative_path(entitlements, 'buildRequirements.entitlements')
    if debugger_entitlement and not entitlements:
        raise ManifestError('debuggerEntitlement requires an entitlements file.')
    requirements = BuildRequirements(lldb_python, debugger_entitlement, entitlements)

    frontend_path = (ROOT / source_directory).resolve()
    if not frontend_path.is_dir() or (ROOT / 'Sources').resolve() not in frontend_path.parents:
        raise ManifestError('frontend source directory must exist under Sources/.')
    if entitlements:
        entitlement_path = (ROOT / entitlements).resolve()
        module_dir = path.parent.resolve()
        if not entitlement_path.is_file() or module_dir not in entitlement_path.parents:
            raise ManifestError('entitlements must exist inside the selected game module.')

    return BuildManifest(runtime, frontend_spec, app_spec, requirements, raw)


def normalized_manifest(manifest: BuildManifest) -> dict:
    return {
        **manifest.runtime.public_metadata(),
        'hostProtocolVersion': HOST_PROTOCOL_VERSION,
        'backend': {'adapter': manifest.runtime.adapter},
        'frontend': {
            'sourceDirectory': manifest.frontend.source_directory,
            'moduleType': manifest.frontend.module_type,
            'architectures': list(manifest.frontend.architectures),
            'minimumMacOS': manifest.frontend.minimum_macos,
        },
        'app': {
            'bundleIdentifier': manifest.app.bundle_identifier,
            'displayName': manifest.app.display_name,
        },
        'buildRequirements': {
            'lldbPython': manifest.requirements.lldb_python,
            'debuggerEntitlement': manifest.requirements.debugger_entitlement,
            'entitlements': manifest.requirements.entitlements,
        },
    }


def swift_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)
