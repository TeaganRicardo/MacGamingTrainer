"""Hades-owned projections of the module's target declaration."""
from pathlib import Path

from core.module_manifest import GameModuleManifest

MODULE_DIR = Path(__file__).resolve().parent


def time_warp_image_names(module_dir=MODULE_DIR):
    manifest = GameModuleManifest.load(Path(module_dir) / 'module.json')
    # Time Warp rewrites imports in the declared executable's image. The
    # suffix is a path identity; its last component is this module's image policy.
    return (Path(manifest.executable_path_suffix).name,)
