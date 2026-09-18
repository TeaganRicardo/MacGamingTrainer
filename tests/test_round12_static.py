from pathlib import Path
import json

root = Path(__file__).resolve().parents[1]
lua = (root/'Backend/games/hades2/runtime/hades.lua').read_text()
adapter = (root/'Backend/games/hades2/adapter.py').read_text()
router = (root/'Backend/games/hades2/command_router.py').read_text()
preparation = (root/'Backend/games/hades2/preparation.py').read_text()
save_service = (root/'Backend/games/hades2/save_service.py').read_text()
localization = (root/'Backend/games/hades2/localization.py').read_text()
config = (root/'Backend/games/hades2/config.py').read_text()
core = '\n'.join(path.read_text() for path in (root/'Backend/core').glob('*.py'))
manifest = json.loads((root/'Backend/games/hades2/module.json').read_text())

# Hades gameplay behavior retained.
for token in ('revision = 26','ActiveProjectileCap = 32','nativeMultiCastControlSet','type(CurrentRun.ResourcesSpent) == "table"','statAvailable = statAvailable'):
    assert token in lua, token

# Game-internal responsibilities are split instead of teaching Core Hades concepts.
assert 'class Hades2Adapter(GameAdapter)' in adapter
assert 'Hades2CommandRouter' in adapter and 'def dispatch' in router
assert 'Hades2PreferenceStore' in adapter and 'Hades2ProfileService' in adapter
assert 'def backup_saves' in save_service and 'def restore_saves' in save_service
assert 'def official_display_names' in localization
assert 'def prepare' in preparation and 'def restore' in preparation
assert len(adapter.splitlines()) < 450
assert len(preparation.splitlines()) < 330
for token in ('CurrentRun','WeaponCast','TraitData','Hades2LuaTransport','SteamSpec','1145350'):
    assert token not in core, token

assert manifest['protocolVersion'] == 5
assert manifest['backend']['adapter'] == 'games.hades2.adapter:Hades2Adapter'
assert manifest['buildRequirements']['lldbPython'] is True
assert 'ui' not in manifest
assert "minimum_architecture='arm64'" in config
print('round12_static_ok')
