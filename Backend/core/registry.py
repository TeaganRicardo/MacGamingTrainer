from importlib import import_module
import logging
from pathlib import Path

from core.adapter import GameAdapter, GameAdapterContext
from core.module_manifest import GameModuleManifest, ManifestError

_ROOT = Path(__file__).resolve().parents[1] / 'games'


def discover_manifests(root: Path = _ROOT, *, selected_game_id=None):
    rows = {}
    root = Path(root)
    backend_root = root.parent
    for path in sorted(root.glob('*/module.json')):
        manifest = None
        try:
            manifest = GameModuleManifest.load(path)
            # A shipped backend validates its own layout, without requiring
            # the frontend/build sources omitted from the App bundle.
            manifest.validate_backend_layout(backend_root)
        except ManifestError:
            if (selected_game_id is None or path.parent.name == selected_game_id
                    or (manifest is not None and manifest.id == selected_game_id)):
                raise
            logging.warning('Unselected game module is invalid: %s', path, exc_info=True)
            continue
        if manifest.id in rows:
            raise ManifestError(f'Duplicate game module id: {manifest.id}')
        rows[manifest.id] = manifest
    return rows


def available_games(root: Path = _ROOT):
    return [manifest.public_metadata() for _, manifest in sorted(discover_manifests(root).items())]


def create_adapter(game_id: str, root: Path = _ROOT):
    try:
        manifest = discover_manifests(root, selected_game_id=game_id)[game_id]
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
        executable_path_suffix=manifest.executable_path_suffix,
    )
    # Do not catch TypeError here: a TypeError raised *inside* a valid adapter
    # constructor is a real module bug and must not be misreported as a bad
    # constructor signature.
    return adapter_type(context=context)
