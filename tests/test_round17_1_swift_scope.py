from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
main = (ROOT / 'Sources/Hades2/Hades2View.swift').read_text()
management = (ROOT / 'Sources/Hades2/Views/Hades2ManagementViews.swift').read_text()

# Hades page-local management state stays out of the parent view. Save-manager
# presentation moved to Core/Host entirely, so its old local state is absent
# from both Hades view files.
for token in ('selectedBackup', 'backupRename', 'selectedProfile'):
    assert token not in main, f'child-local state leaked back into Hades2View: {token}'

for token in ('selectedBackup', 'backupRename', 'model.backups', 'Hades2SaveManagerView'):
    assert token not in management, token

for token in (
    '@State private var selectedProfile',
    '.onChange(of: model.profiles.map(\\.name), initial: true)',
):
    assert token in management, token

# Keep the top-level body tiny. Splitting long observer chains into opaque view
# boundaries prevents SwiftUI's constraint solver from having to solve dozens
# of onChange modifiers as one expression.
body = re.search(r'var body: some View\s*\{(?P<body>.*?)\n\s*\}', main, re.S)
assert body, 'Hades2TrainerView body not found'
assert 'editorGenerationObservedContent' in body.group('body')
assert '.onChange(' not in body.group('body')

for name in (
    'connectionObservedContent',
    'statObservedContent',
    'gameConfigObservedContent',
    'catalogObservedContent',
    'editorGenerationObservedContent',
):
    assert f'private var {name}: some View' in main, name

print('round17_1_swift_scope_ok')

# Runtime observation must not be routed through edit/mutation observers.
assert 'private var inputObservedContent' not in main
assert 'private var lockedStatObservedContent' not in main
assert 'applyInputChanges' not in main
assert 'applyLockedStatChanges' not in main
assert 'intentBinding(' in main

assert '.onChange(of: model.editGeneration)' in main
assert 'rebuildEditorDraftsFromModel()' in main

assert 'editedConfigDrafts' in main
assert 'configIntentBinding(' in main
assert 'editedConfigDrafts.removeAll()' in main
