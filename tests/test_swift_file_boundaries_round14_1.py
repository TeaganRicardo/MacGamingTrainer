from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
swift_files = sorted((root / 'Sources').rglob('*.swift'))
texts = {path: path.read_text() for path in swift_files}

private_type = re.compile(r'^private\s+(?:struct|class|enum|protocol|actor|typealias)\s+([A-Za-z_][A-Za-z0-9_]*)', re.M)
violations = []
for owner, text in texts.items():
    for name in private_type.findall(text):
        token = re.compile(rf'\b{re.escape(name)}\b')
        for other, other_text in texts.items():
            if other != owner and token.search(other_text):
                violations.append(f'{name}: private in {owner.relative_to(root)}, referenced by {other.relative_to(root)}')
assert not violations, '\n'.join(violations)

model = texts[root / 'Sources/Hades2/Hades2Model.swift']
view = texts[root / 'Sources/Hades2/Hades2View.swift']
picker = texts[root / 'Sources/Core/UI/Components/TrainerResourceControls.swift']
assert 'ResourceSectionGroup' not in model + view
assert 'BoonSectionGroup' not in model + view
assert 'TrainerGroupedOptionPicker' in picker
assert 'TrainerGroupedOptionPicker' in view
assert 'Hades2BoonPicker' not in view

print('swift_file_boundaries_round14_1_ok')
