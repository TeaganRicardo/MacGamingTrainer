from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SWIFT = sorted((ROOT / 'Sources').rglob('*.swift'))
TEXT = '\n'.join(path.read_text() for path in SWIFT)

# Custom project types must have an in-tree declaration. This catches stale
# cross-file type names that plain `swiftc -parse` cannot diagnose.
declared = set(re.findall(r'\b(?:struct|class|enum|protocol|actor|typealias)\s+([A-Z][A-Za-z0-9_]*)', TEXT))
custom_uses = set(re.findall(
    r'\b(?:Hades2[A-Z][A-Za-z0-9_]*|Trainer[A-Z][A-Za-z0-9_]*|Element[A-Z][A-Za-z0-9_]*|MaterialResource|BoonOption|ShortcutAction|SaveBackup|DiagnosticCheck)\b',
    TEXT,
))
unresolved = sorted(custom_uses - declared)
assert not unresolved, f'unresolved custom Swift types: {unresolved}'
assert 'ElementAmount' not in TEXT
assert 'ElementCount' in declared

# Hades views may only reference members that actually exist somewhere on the
# model (including model extensions). This catches another class of split-file
# semantic errors that syntax parsing alone misses.
hades_text = '\n'.join(path.read_text() for path in (ROOT / 'Sources/Hades2').rglob('*.swift'))
model_member_decls = set(re.findall(r'\b(?:var|let|func)\s+([A-Za-z_][A-Za-z0-9_]*)', hades_text))
model_member_uses = set(re.findall(r'\bmodel\.([A-Za-z_][A-Za-z0-9_]*)', hades_text))
missing_model_members = sorted(model_member_uses - model_member_decls)
assert not missing_model_members, f'unresolved Hades2TrainerModel members: {missing_model_members}'

api_text = (ROOT / 'Sources/Hades2/Hades2API.swift').read_text()
model_text = (ROOT / 'Sources/Hades2/Hades2Model.swift').read_text()
api_methods = set(re.findall(r'\bfunc\s+([A-Za-z_][A-Za-z0-9_]*)', api_text))
api_uses = set(re.findall(r'\bapi\.([A-Za-z_][A-Za-z0-9_]*)', model_text))
missing_api_methods = sorted(api_uses - api_methods)
assert not missing_api_methods, f'unresolved Hades2API methods: {missing_api_methods}'

view = (ROOT / 'Sources/Hades2/Hades2View.swift').read_text()
snapshots = (ROOT / 'Sources/Hades2/Views/Hades2ViewSnapshots.swift').read_text()

# Keep the primary Hades view cheap for SwiftUI's constraint solver. Model ->
# editor synchronization is intentionally aggregated into snapshot observers.
assert view.count('.onChange(') <= 8, f'too many Hades2View onChange modifiers: {view.count(".onChange(")}'
for name in (
    'Hades2ViewConnectionSnapshot', 'Hades2ViewStatSnapshot', 'Hades2ViewConfigSnapshot',
    'Hades2ViewInputSnapshot', 'Hades2ViewLockedStatInputSnapshot', 'Hades2ViewCatalogSnapshot',
):
    assert f'struct {name}' in snapshots
    assert name in view
for token in ('statusAndSessionSection', 'combatSection', 'buildSection', 'resourceSection', 'spawnSection', 'expandedSessionMetrics'):
    assert token in view, token

# Formatting is kept out of SwiftUI onChange closures; older Swift 6.4 builds
# have shown pathological solver behaviour around the previous inline form.
observer_zone = view[view.index('private var connectionObservedContent'):view.index('private func resetEditorInputs')]
assert 'String(format:' not in observer_zone

# The experimental Finder build helper was removed in v0.17.3 after real
# macOS permission/path failures. Manual build.sh is the supported path.
assert not (ROOT / 'Build Trainer.app').exists()

# Hades2View helper calls must close over declarations in the same type. This
# catches refactor regressions such as deleting syncElementInputs while leaving
# its call site behind; plain Swift parsing accepts such unresolved names.
helper_calls = set(re.findall(r'(?<![.$A-Za-z0-9_])([a-z_][A-Za-z0-9_]*)\s*\(', view))
helper_decls = set(re.findall(r'\bfunc\s+([a-z_][A-Za-z0-9_]*)\s*\(', view))
helper_prefixes = (
    'sync', 'apply', 'reset', 'open', 'editable', 'feature', 'section',
    'spawn', 'multiplier', 'stat', 'elementMetric', 'compact', 'speed',
    'number', 'pair', 'resource', 'message',
)
missing_helpers = sorted(
    name for name in helper_calls
    if name.startswith(helper_prefixes) and name not in helper_decls
)
assert not missing_helpers, f'unresolved Hades2View helper calls: {missing_helpers}'
assert 'private func syncElementInputs(_ values: [ElementCount])' in view

# Parse the entire source graph with the generated active-game binding.
swiftc = shutil.which('swiftc')
if swiftc:
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        generated = td / 'ActiveGame.generated.swift'
        subprocess.run(['python3', str(ROOT / 'Tools/generate_game_binding.py'), 'hades2', str(generated)], check=True)
        sources = [ROOT / 'Sources/App.swift'] + sorted((ROOT / 'Sources/Core').rglob('*.swift')) + sorted((ROOT / 'Sources/Hades2').rglob('*.swift')) + [generated]
        subprocess.run([swiftc, '-frontend', '-parse', *map(str, sources)], check=True)

        # Foundation-only semantic slice: this catches actual symbol/type errors
        # in Runtime + typed Hades protocol/state/services on Linux as well.
        descriptor_stub = td / 'GameModuleDescriptor.swift'
        descriptor_stub.write_text('''
import Foundation
struct GameModuleDescriptor {
    let id: String
    let displayName: String
    let backendGameID: String
    let expectedHostProtocolVersion: Int
    let expectedModuleProtocolVersion: Int
}
''')
        foundation_sources = [
            ROOT / 'Sources/Core/Runtime/BackendProcess.swift',
            ROOT / 'Sources/Core/Runtime/BackendClient.swift',
            descriptor_stub,
            ROOT / 'Sources/Core/Runtime/TrainerBackendSession.swift',
            ROOT / 'Sources/Hades2/Hades2Types.swift',
            ROOT / 'Sources/Hades2/Hades2API.swift',
            ROOT / 'Sources/Hades2/Hades2BackendState.swift',
            ROOT / 'Sources/Hades2/Services/Hades2MutationScheduler.swift',
            ROOT / 'Sources/Hades2/Services/Hades2ShortcutStore.swift',
            ROOT / 'Sources/Hades2/Views/Hades2ViewSnapshots.swift',
        ]
        subprocess.run([swiftc, '-typecheck', *map(str, foundation_sources)], check=True)

print('swift_integrity_v0172_ok')
