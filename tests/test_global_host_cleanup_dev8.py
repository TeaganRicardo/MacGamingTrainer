from pathlib import Path
import json
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))

from games.hades2.persistence import UnsupportedSchemaVersionError
from games.hades2.profile_service import PROFILE_SCHEMA_VERSION, Hades2ProfileService


def read(path):
    return (ROOT / path).read_text(encoding='utf-8')


# Retired product surface is removed end-to-end instead of kept as protocol shims.
product_text = '\n'.join([
    read('Sources/Hades2/Hades2API.swift'),
    read('Sources/Hades2/Hades2Model.swift'),
    read('Sources/Hades2/Hades2BackendState.swift'),
    read('Backend/games/hades2/adapter.py'),
    read('Backend/games/hades2/command_router.py'),
    read('Backend/games/hades2/runtime/hades.lua'),
])
for retired in ('boonChoice', 'set_boon_choice', 'spawn_boon', 'add_resource'):
    assert retired not in product_text, retired
manifest = json.loads(read('Backend/games/hades2/module.json'))
assert manifest['protocolVersion'] == 5

# Profiles are current-schema-only. Unsupported old files are left alone and an
# explicit same-name save replaces them with the current schema in one atomic write.
base = Path(tempfile.mkdtemp(prefix='mgt-dev8-profile-'))
profiles = Hades2ProfileService(base / 'profiles')
old = profiles.path('old')
old.write_text(json.dumps({'name':'old','desired':{'godMode':True}}), encoding='utf-8')
old_bytes = old.read_bytes()
try:
    profiles.load('old')
except UnsupportedSchemaVersionError:
    pass
else:
    raise AssertionError('legacy Profile remained loadable')
assert old.read_bytes() == old_bytes
profiles.save('old', {'godMode':False}, {'godMode':1})
assert json.loads(old.read_text())['schemaVersion'] == PROFILE_SCHEMA_VERSION

# Target application identity is a module contract and flows into the generated
# global host descriptor; process lifecycle is event-driven, never timer-polled.
manifest_core = read('Backend/core/module_manifest.py')
generator = read('Tools/generate_game_binding.py')
monitor = read('Sources/Core/Runtime/TrainerTargetProcessMonitor.swift')
host = read('Sources/Core/Host/TrainerHost.swift')
app = read('Sources/App.swift')
for token in ('process_name', 'bundle_identifier', 'targetApplication'):
    assert token in manifest_core, token
for token in ('targetProcessName', 'targetBundleIdentifier'):
    assert token in generator, token
assert 'NSWorkspace.didLaunchApplicationNotification' in monitor
assert 'NSWorkspace.didTerminateApplicationNotification' in monitor
assert 'NSWorkspace.didActivateApplicationNotification' in monitor
assert 'activationGeneration' in monitor
assert 'Timer.' not in monitor and 'scheduledTimer' not in monitor
assert 'TrainerConnectionPolicy()' in host
assert 'connectionPolicy.targetStateChanged' in host
assert 'connectionPolicy.userWillToggleConnection' in host
assert 'connectionPolicy.backendBecameUnavailable' in host
assert 'consumeAutomaticBackendRestartIfEligible' in host
assert 'model.restartBackendFromHost()' in host
assert 'handlePrimaryConnectionAction' in host
assert 'TrainerConnectionPolicy.swift' in [p.name for p in (ROOT / 'Sources/Core/Host').iterdir()]
assert 'model.toggleConnectionFromHost()' in host
assert 'targetMonitor.isRunning' in host
assert 'NSApp.activate(ignoringOtherApps:' not in app
assert 'frontmostApplication' not in app
assert 'model.toggleConnectionFromHost()' not in app
assert 'Timer.' not in host and 'scheduledTimer' not in host

# Backend failures are globally recovered with bounded retries. Terminal client
# errors enter recovery state; non-terminal overload remains a normal user error.
client = read('Sources/Core/Runtime/BackendClient.swift')
session = read('Sources/Core/Runtime/TrainerBackendSession.swift')
assert 'onClientError: @escaping (String, Bool) -> Void' in client
assert '队列已满' in client and ', false)' in client
assert '请求「' in client and ', true)' in client
assert 'maximumAutomaticRecoveryAttempts = 2' in session
assert '后端通信异常，正在自动恢复' in session
assert '$0.error = ""' in session
assert 'protocolCompatible' in read('Sources/Hades2/Hades2Model.swift').split('hostActionsEnabled', 1)[1].split('\n', 1)[0]

# Hot stdout/log paths avoid repeated prefix shifts and per-line file reopen.
process = read('Sources/Core/Runtime/BackendProcess.swift')
log_sink = read('Sources/Core/Runtime/TrainerLogSink.swift')
assert process.count('buffer.removeSubrange(') == 1
assert 'var cursor = buffer.startIndex' in process
assert 'private var handle: FileHandle?' in log_sink
assert 'ensureHandle()' in log_sink
assert 'deinit {' in log_sink and 'deinit {\n        queue.sync' not in log_sink

# Hades runtime caches only static catalog shape. Dynamic counts and lock state
# are still rebuilt for each state snapshot, while the hot AddResource hook no
# longer constructs the full Inventory model for every resource event.
lua = read('Backend/games/hades2/runtime/hades.lua')
for token in ('catalogCache = {}', 'local function resourceCatalog()', 'M.catalogCache.resources', 'M.catalogCache.boons', 'M.catalogCache.rewards'):
    assert token in lua, token
assert 'local _, allowed = resources()' not in lua
assert 'local _, _, allowed = resourceCatalog()' in lua

# Global UI owns page geometry, connection chrome, section heading/accessory,
# and sheet chrome. Hades consumes these primitives rather than copying them.
theme = read('Sources/Core/UI/TrainerTheme.swift')
status_components = read('Sources/Core/UI/StatusComponents.swift')
sheet = read('Sources/Core/UI/Components/TrainerSheetScaffold.swift')
hades_view = read('Sources/Hades2/Hades2View.swift')
management = read('Sources/Hades2/Views/Hades2ManagementViews.swift')
save_view = read('Sources/Core/Save/TrainerSaveManagerView.swift')
for token in ('contentMinWidth', 'contentMinHeight', 'pageMaxWidth', 'pagePadding', 'pageSpacing', 'panelPadding', 'rowHorizontalPadding', 'rowMinimumHeight', 'sheetPadding', 'sheetSpacing', 'emptyStatePadding'):
    assert token in theme, token
assert 'TrainerConnectionStatusCard(' in host
assert 'TrainerConnectionStatusCard(' not in hades_view
assert 'struct TrainerSectionHeader' in status_components
assert 'TrainerRow(opacity:' in read('Sources/Core/UI/Components/TrainerFeatureControls.swift')
assert 'TrainerRow(opacity:' in read('Sources/Core/UI/Components/TrainerStatControls.swift')
assert 'TrainerSectionHeader(' in hades_view
assert 'struct TrainerSheetScaffold' in sheet
assert management.count('TrainerSheetScaffold(') == 3
assert management.count('TrainerEmptyState(') == 1
assert 'TrainerSheetScaffold(' in save_view
assert 'TrainerEmptyState(' in save_view
assert '.padding(28)' not in management
assert '.frame(minWidth: 760, minHeight: 740)' not in hades_view
assert 'contentMinWidth' in host and 'contentMinHeight' in host
assert 'func connectFromHost' not in read('Sources/Core/Host/TrainerGameModule.swift')

print('global_host_cleanup_dev8_ok')
