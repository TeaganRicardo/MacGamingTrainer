"""Every Python helper a macOS inventory test imports or runs is declared for it.

CI routes a changed support file to its native consumers only through
Tools/macos_test_dependencies.json. An undeclared helper classifies as
portable-only, so changing it runs none of the native journeys that use it.
Derive each consumer's helpers from its source and require the declaration.
"""
import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / 'tests'
INVENTORY = [line.strip() for line in (ROOT / 'Tools/macos_only_tests.txt').read_text().splitlines()
             if line.strip()]
DECLARED = json.loads((ROOT / 'Tools/macos_test_dependencies.json').read_text())
# Native sources under tests/ already route every inventory test (see
# Tools/select_macos_pr_tests.py), so only Python/data helpers need edges.
FIXTURE_LITERAL = re.compile(r"""['"/]((?:tests/)?fixtures/[\w./-]+?\.(?:py|lua|json))['"]""")
FIXTURE_JOINED = re.compile(
    r"""fixtures['"]\s*/\s*['"]([\w-]+)['"]\s*/\s*['"]([\w.-]+\.(?:py|lua|json))['"]""")


def helpers(path, seen):
    if path in seen:
        return set()
    seen.add(path)
    source = path.read_text(encoding='utf-8')
    found = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules = [node.module]
        else:
            continue
        for module in modules:
            candidate = TESTS / (module.split('.')[0] + '.py')
            if candidate.is_file() and candidate != path:
                found.add(candidate)
                found |= helpers(candidate, seen)
    for match in FIXTURE_LITERAL.finditer(source):
        relative = match.group(1)
        candidate = ROOT / (relative if relative.startswith('tests/') else 'tests/' + relative)
        if candidate.is_file():
            found.add(candidate)
    for match in FIXTURE_JOINED.finditer(source):
        candidate = TESTS / 'fixtures' / match.group(1) / match.group(2)
        if candidate.is_file():
            found.add(candidate)
    return found


undeclared = {}
for name in INVENTORY:
    required = {path.relative_to(ROOT).as_posix() for path in helpers(TESTS / name, set())}
    missing = sorted(required - set(DECLARED.get(name, [])))
    if missing:
        undeclared[name] = missing
assert not undeclared, (
    'declare these helpers in Tools/macos_test_dependencies.json so CI runs their '
    f'native consumers: {json.dumps(undeclared, indent=1)}'
)
print('macos_test_dependency_inventory_ok')
