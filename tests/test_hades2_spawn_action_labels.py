"""Spawn rows cannot omit the live, module-owned Generate label.

SwiftUI is not available to portable CI. Keep this small structural check at
its presentation boundary, alongside the shipped localization contract; the
macOS build checks the real SwiftUI call and the final user run checks visuals.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / 'Sources/Hades2/Hades2View.swift').read_text(encoding='utf-8')
row = re.search(
    r'private func spawnRow\((.*?)\)\s*->\s*some View\s*\{(.*?)\n    \}',
    source,
    re.DOTALL,
)
assert row is not None, 'Locate the actual shared Spawn row presentation boundary.'
parameters, body = row.groups()
assert 'actionTitle' not in parameters, 'Spawn rows must not accept an optional or blank action title.'
label = re.search(r'actionTitle:\s*text\("([^"]+)"\)', body)
assert label is not None, 'The picker action must resolve its label through the live language helper.'
assert label.group(1) == 'hades2.spawn.generate', 'All Spawn actions use the module-owned Generate term.'

panel = source.split('private var boonPanel: some View {', 1)[1].split('private func spawnRow(', 1)[0]
for action, callback in (
    ('spawnOlympian', 'spawnBoon'),
    ('spawnPickup', 'spawnBoon'),
    ('spawnSpecial', 'performSpecialReward'),
):
    assert re.search(
        rf'spawnRow\((?:(?!spawnRow\().)*?shortcut:\s*\.{action}\b'
        rf'(?:(?!spawnRow\().)*?onAction:\s*model\.{callback}\b',
        panel,
        re.DOTALL,
    ), f'{action} must use the shared labeled row and retain its existing command callback.'

for language in ('zh-CN', 'en'):
    table = json.loads((ROOT / 'Sources/Hades2/Presentation/Localization' / f'hades2.{language}.json').read_text(encoding='utf-8'))['entries']
    value = table.get(label.group(1))
    assert isinstance(value, str) and value.strip(), f'{language}: Generate must not render blank.'

print('hades2_spawn_action_labels_ok')
