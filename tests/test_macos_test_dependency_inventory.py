"""Every test-support file a macOS inventory test imports or runs routes to it.

A changed file under tests/ reaches its native consumers only through the edges
in Tools/macos_test_dependencies.json. An undeclared helper or fixture classifies
as portable-only, so changing it runs none of the native journeys that use it.
Derive each consumer's helpers from its source and require that the PR routing
owners select that consumer when the helper changes.
"""
import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / 'tests'
sys.path.insert(0, str(ROOT / 'Tools'))

from ci_docs_only import is_linux_portable_only, load_macos_only_tests
from select_macos_pr_tests import selected_tests, source_directories

INVENTORY = load_macos_only_tests()
SOURCES = source_directories()
# A file reference is a relative path literal; prose and embedded sources are not.
PATH_LITERAL = re.compile(r'[\w.-]+(?:/[\w.-]+)*')


def tests_file(relative):
    candidate = (TESTS / relative).resolve()
    return candidate if candidate.is_file() and TESTS in candidate.parents else None


def imported_module(dotted):
    path = dotted.replace('.', '/')
    return tests_file(path + '.py') or tests_file(path + '/__init__.py')


def path_parts(node):
    """String parts of a `base / 'a' / 'b.py'` chain after its last non-literal."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        return path_parts(node.left) + path_parts(node.right)
    return []


def helpers(path, seen):
    """Repository files under tests/ that `path` imports or names, transitively."""
    if path in seen:
        return set()
    seen.add(path)
    found = set()
    for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
        candidates = []
        if isinstance(node, ast.Import):
            candidates = [imported_module(alias.name) for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            candidates = [imported_module(node.module)] + [
                imported_module(f'{node.module}.{alias.name}') for alias in node.names]
        elif isinstance(node, (ast.Constant, ast.BinOp)):
            relative = '/'.join(path_parts(node))
            if PATH_LITERAL.fullmatch(relative):
                candidates = [tests_file(relative), tests_file(relative.removeprefix('tests/'))
                              if relative.startswith('tests/') else None]
        for candidate in candidates:
            if candidate is not None and candidate != path:
                found.add(candidate)
                if candidate.suffix == '.py':
                    found |= helpers(candidate, seen)
    return found


unrouted = {}
for consumer in sorted(INVENTORY):
    for helper in sorted(helpers(TESTS / consumer, set()) - {TESTS / consumer}):
        relative = helper.relative_to(ROOT).as_posix()
        if is_linux_portable_only(relative, INVENTORY) or consumer not in selected_tests(
                [relative], INVENTORY, SOURCES):
            unrouted.setdefault(consumer, []).append(relative)
assert not unrouted, (
    'declare these helpers for their consumers in Tools/macos_test_dependencies.json so '
    f'PR routing runs the native tests that use them: {json.dumps(unrouted, indent=1)}'
)
print('macos_test_dependency_inventory_ok')
