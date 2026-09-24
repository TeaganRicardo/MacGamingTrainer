import json
from dataclasses import dataclass
from pathlib import Path

from core.game_spec import GameSpec
from core.module_manifest import GameModuleManifest


@dataclass(frozen=True)
class SteamSpec:
    app_id: str
    steamapps_path: Path

    @property
    def manifest_path(self) -> Path:
        return self.steamapps_path / f"appmanifest_{self.app_id}.acf"

    @property
    def launch_url(self) -> str:
        return f"steam://rungameid/{self.app_id}"


MODULE_DIR = Path(__file__).resolve().parent
MODULE_MANIFEST = GameModuleManifest.load(MODULE_DIR / 'module.json')

HOME = Path.home()
STEAMAPPS = HOME / 'Library/Application Support/Steam/steamapps'
_RAW_MODULE = json.loads((MODULE_DIR / 'module.json').read_text(encoding='utf-8'))
STEAM_APP_ID = _RAW_MODULE.get('steamAppId')
if not isinstance(STEAM_APP_ID, str) or not STEAM_APP_ID.isdigit():
    raise RuntimeError('Hades II module manifest is missing a valid steamAppId.')
GAME_SPEC = GameSpec.macos_app_bundle(
    id=MODULE_MANIFEST.id,
    display_name=MODULE_MANIFEST.display_name,
    process_name=MODULE_MANIFEST.process_name,
    bundle_identifier=MODULE_MANIFEST.bundle_identifier,
    app_path=STEAMAPPS / 'common/Hades II/Hades II.app',
    executable_name='Hades II',
    save_path=HOME / 'Library/Application Support/Supergiant Games/Hades II',
    minimum_architecture='arm64',
)
STEAM_SPEC = SteamSpec(app_id=STEAM_APP_ID, steamapps_path=STEAMAPPS)

# Preserve the existing Hades II data location. New game modules should use a
# namespaced directory under MacGamingTrainer/<game-id> unless migration requires otherwise.
DATA = HOME / 'Library/Application Support/MacGamingTrainer'
