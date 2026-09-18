from pathlib import Path
import collections
import re

ROOT = Path(__file__).resolve().parents[1]
rows = []
pattern = re.compile(
    r'(?m)^(?:public\s+|internal\s+|private\s+|fileprivate\s+)?'
    r'(?:struct|class|final\s+class|enum|protocol|actor|typealias)\s+'
    r'([A-Za-z_][A-Za-z0-9_]*)'
)
for path in sorted((ROOT / 'Sources').rglob('*.swift')):
    text = path.read_text()
    for match in pattern.finditer(text):
        rows.append((
            match.group(1),
            str(path.relative_to(ROOT)),
            text.count('\n', 0, match.start()) + 1,
        ))

by_name = collections.defaultdict(list)
for name, path, line in rows:
    by_name[name].append((path, line))

duplicates = {name: locations for name, locations in by_name.items() if len(locations) > 1}
assert not duplicates, f'duplicate top-level Swift declarations: {duplicates}'

# The section heading has one canonical implementation in StatusComponents.
section_heading = by_name.get('TrainerSectionHeading', [])
assert section_heading == [('Sources/Core/UI/StatusComponents.swift', 3)], section_heading
assert 'TrainerSectionHeading' not in (ROOT / 'Sources/Core/UI/Components/TrainerStatControls.swift').read_text()

print('swift_declaration_uniqueness_v0176_ok')
