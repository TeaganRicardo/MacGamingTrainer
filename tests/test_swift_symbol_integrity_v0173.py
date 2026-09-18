from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
view_path = ROOT / 'Sources/Hades2/Hades2View.swift'
view = view_path.read_text()

# Fast source-level helper closure check.
helper_calls = set(re.findall(r'(?<![.$A-Za-z0-9_])([a-z_][A-Za-z0-9_]*)\s*\(', view))
helper_decls = set(re.findall(r'\bfunc\s+([a-z_][A-Za-z0-9_]*)\s*\(', view))
helper_prefixes = (
    'sync', 'apply', 'reset', 'open', 'editable', 'feature', 'section',
    'spawn', 'multiplier', 'stat', 'elementMetric', 'compact', 'speed',
    'number', 'pair', 'resource', 'message',
)
missing = sorted(name for name in helper_calls if name.startswith(helper_prefixes) and name not in helper_decls)
assert not missing, f'missing Hades2View helper declarations: {missing}'

# Parser-assisted unresolved-symbol approximation. Parse-only Swift accepts
# unknown names, but its syntax tree exposes unresolved_decl_ref_expr nodes.
# After subtracting locals/members and known stdlib globals, no lowercase bare
# identifier should remain in the main Hades view.
swiftc = shutil.which('swiftc')
if swiftc:
    proc = subprocess.run([swiftc, '-frontend', '-dump-parse', str(view_path)], capture_output=True, text=True, check=True)
    unresolved = set(re.findall(r'unresolved_decl_ref_expr[^\n]*name="([^"]+)"', proc.stdout))
    declared = set(re.findall(r'\b(?:var|let|func|struct|class|enum|protocol|typealias|case)\s+([A-Za-z_][A-Za-z0-9_]*)', view))
    declared |= set(re.findall(r'\b([A-Za-z_][A-Za-z0-9_]*)\s*:', view))
    declared |= set(re.findall(r'\bfor\s+([A-Za-z_][A-Za-z0-9_]*)\s+in\b', view))
    for match in re.finditer(r'\{\s*([^{}\n]+?)\s+in\b', view):
        declared |= set(re.findall(r'\b([A-Za-z_][A-Za-z0-9_]*)\b', match.group(1)))
    known = {'withAnimation', 'max', 'min', 'abs'}
    suspicious = sorted(name for name in unresolved if name and name[0].islower() and name not in declared and name not in known)
    assert not suspicious, f'suspicious unresolved lowercase identifiers in Hades2View: {suspicious}'

assert 'syncElementInputs(snapshot.elements)' in view
assert 'private func syncElementInputs(_ values: [ElementCount])' in view
assert 'ElementAmount' not in view
assert not (ROOT / 'Build Trainer.app').exists()
print('swift_symbol_integrity_v0173_ok')
