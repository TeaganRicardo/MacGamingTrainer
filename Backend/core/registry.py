from importlib import import_module
from pathlib import Path

from core.module_manifest import GameModuleManifest, ManifestError
from core.adapter import GameAdapter, GameAdapterContext

_ROOT = Path(__file__).resolve().parents[1] / 'games'


def discover_manifests(root: Path = _ROOT):
    rows = {}
    root = Path(root)
    backend_root = root.parent
    for path in sorted(root.glob('*/module.json')):
        manifest = GameModuleManifest.load(path)
        # Runtime discovery validates only the packaged Backend tree. Full
        # frontend/entitlements checks belong to the build tool because Sources/
        # is intentionally absent from a shipped .app.
        manifest.validate_backend_layout(backend_root)
        if manifest.id in rows:
            raise ManifestError(f'Duplicate game module id: {manifest.id}')
        rows[manifest.id] = manifest
    return rows


def available_games(root: Path = _ROOT):
    return [manifest.public_metadata() for _, manifest in sorted(discover_manifests(root).items())]


def create_adapter(game_id: str, root: Path = _ROOT):
    try:
        manifest = discover_manifests(root)[game_id]
    except KeyError as error:
        raise ValueError(f'不支持的游戏模块：{game_id}') from error
    module_name, class_name = manifest.adapter.split(':', 1)
    module = import_module(module_name)
    adapter_type = getattr(module, class_name, None)
    if not isinstance(adapter_type, type) or not issubclass(adapter_type, GameAdapter):
        raise TypeError(f'Adapter {manifest.adapter} must inherit GameAdapter.')
    context = GameAdapterContext(
        game_id=manifest.id,
        display_name=manifest.display_name,
        module_protocol_version=manifest.module_protocol_version,
        module_dir=manifest.source_path.parent,
        public_metadata=manifest.public_metadata(),
        process_name=manifest.process_name,
        save_management=manifest.save_management,
    )
    # Do not catch TypeError here: a TypeError raised *inside* a valid adapter
    # constructor is a real module bug and must not be misreported as a bad
    # constructor signature.
    return adapter_type(context=context)
