from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
core_swift = '\n'.join(p.read_text() for p in sorted((root/'Sources/Core').rglob('*.swift')))
app = (root/'Sources/App.swift').read_text()
hades_model = (root/'Sources/Hades2/Hades2Model.swift').read_text()
hades_view = (root/'Sources/Hades2/Hades2View.swift').read_text()
hades_api = (root/'Sources/Hades2/Hades2API.swift').read_text()
hades_state = (root/'Sources/Hades2/Hades2BackendState.swift').read_text()
hades_presentation = (root/'Sources/Hades2/Presentation/Hades2FeaturePresentation.swift').read_text()
manifest_core = (root/'Backend/core/module_manifest.py').read_text()
tool_support = (root/'Tools/module_support.py').read_text()
adapter = (root/'Backend/games/hades2/adapter.py').read_text()

# Core UI is visual infrastructure, not a genericized copy of Hades semantics.
for token in ('desiredFeatures','dormantFeatures','statSupport','statAvailable','boonRarity','enemyHealth','rerollsLocked','godMode'):
    assert token not in core_swift, token
for forbidden_business_semantic in ('TrainerFeatureState','desiredFeatures','dormantFeatures','statAvailable','boonRarity','enemyHealth'):
    assert forbidden_business_semantic not in core_swift, forbidden_business_semantic
for primitive in ('TrainerMetricCard','TrainerRow','TrainerToggleControl','TrainerNumberField','TrainerMessageBanner','TrainerSheetScaffold','TrainerSection'):
    assert primitive in core_swift, primitive

# Global chrome and application termination cannot be opted out of by a game.
assert 'TrainerHostView<ActiveGameModule>' in app
assert 'NSApp.reply(toApplicationShouldTerminate:' in app
assert 'TrainerShell' in (root/'Sources/Core/Host/TrainerHost.swift').read_text()
assert 'TrainerShell' not in hades_view and 'TrainerSidebar' not in hades_view
assert 'NSApp.reply' not in hades_model

# Hades maps its own lifecycle semantics to visual state locally.
for token in ('dormant','activationPending','waiting','mismatch'):
    assert token in hades_presentation, token

# Command spelling/parameter keys are centralized in the game API; Views never
# send raw backend commands and Model does not contain protocol command strings.
assert 'enum Hades2Request' in hades_api
assert 'var params: [String: Any]' in hades_api
assert 'model.send' not in hades_view
for command in ('"set_stat"','"set_resource"','"set_desired"'):
    assert command not in hades_model, command
# Raw payload field decoding is isolated in the typed state boundary.
assert 'struct Hades2StatePatch' in hades_state
assert 'numberField(payload, "health")' in hades_state
assert 'payload["health"]' not in hades_model
assert 'payload["featureSupport"]' not in hades_model

# Runtime Backend core understands only runtime module identity. Build/UI schema
# belongs to Tools, not to the process that serves JSONL at runtime.
import sys
from dataclasses import fields
sys.path.insert(0, str(root/'Backend'))
from core.module_manifest import GameModuleManifest
assert {field.name for field in fields(GameModuleManifest)} == {
    'id','display_name','module_protocol_version','adapter','process_name','bundle_identifier','source_path','save_management'
}
for token in ('FrontendBuildSpec','architectures','bundle_identifier','entitlements','module_type'):
    assert token in tool_support, token

# Hades backend adapter is lifecycle/replay, not profiles+saves+diagnostics+all
# command validation in one class. Save management is a Core service now.
for file in ('command_router.py','preferences.py','profile_service.py','localization.py','catalog.py','diagnostics.py'):
    assert (root/'Backend/games/hades2'/file).is_file(), file
assert not (root/'Backend/games/hades2/save_service.py').exists()
assert (root/'Backend/core/save_service.py').is_file()
assert 'Hades2CommandRouter' in adapter

print('global_decoupling_round15_ok')
