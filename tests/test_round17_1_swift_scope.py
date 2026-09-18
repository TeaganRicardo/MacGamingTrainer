from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
main = (ROOT / 'Sources/Hades2/Hades2View.swift').read_text()
management = (ROOT / 'Sources/Hades2/Views/Hades2ManagementViews.swift').read_text()

# These states were moved into management subviews in Round 16. The parent view
# must never observe them directly; plain Swift parsing cannot detect this kind
# of cross-scope reference, while macOS semantic type-checking can.
for token in ('selectedBackup', 'backupRename', 'selectedProfile'):
    assert token not in main, f'child-local state leaked back into Hades2View: {token}'

for token in (
    '@State private var selectedBackup',
    '@State private var backupRename',
    '@State private var selectedProfile',
    '.onChange(of: model.backups.map(\\.id), initial: true)',
    '.onChange(of: selectedBackup, initial: true)',
    '.onChange(of: model.profiles.map(\\.name), initial: true)',
):
    assert token in management, token

# Keep the top-level body tiny. Splitting long observer chains into opaque view
# boundaries prevents SwiftUI's constraint solver from having to solve dozens
# of onChange modifiers as one expression.
body = re.search(r'var body: some View\s*\{(?P<body>.*?)\n\s*\}', main, re.S)
assert body, 'Hades2TrainerView body not found'
assert 'catalogObservedContent' in body.group('body')
assert '.onChange(' not in body.group('body')

for name in (
    'connectionObservedContent',
    'statObservedContent',
    'gameConfigObservedContent',
    'inputObservedContent',
    'lockedStatObservedContent',
    'catalogObservedContent',
):
    assert f'private var {name}: some View' in main, name

print('round17_1_swift_scope_ok')
