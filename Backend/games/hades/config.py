"""Hades-owned projections of the module's target declaration."""
import json
from pathlib import Path

from core.module_manifest import GameModuleManifest

MODULE_DIR = Path(__file__).resolve().parent


def steam_launch_url(module_dir):
    manifest = json.loads((Path(module_dir) / 'module.json').read_text(encoding='utf-8'))
    app_id = manifest.get('steamAppId')
    if not isinstance(app_id, str) or not app_id.isdigit():
        raise RuntimeError('Hades module manifest is missing a valid steamAppId.')
    return f'steam://run/{app_id}'


def time_warp_image_names(module_dir=MODULE_DIR):
    manifest = GameModuleManifest.load(Path(module_dir) / 'module.json')
    # Time Warp rewrites imports in the declared executable's image. The
    # suffix is a path identity; its last component is this module's image policy.
    return (Path(manifest.executable_path_suffix).name,)
