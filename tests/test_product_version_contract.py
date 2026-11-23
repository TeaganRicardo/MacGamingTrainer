import json
import plistlib
import re
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.9/3.10 compatibility
    tomllib = None

ROOT = Path(__file__).resolve().parents[1]
plist = plistlib.loads((ROOT / 'Info.plist').read_bytes())
version = plist['CFBundleShortVersionString']
build_version = plist['CFBundleVersion']

assert re.fullmatch(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)', version), version
assert re.fullmatch(r'[1-9][0-9]*', build_version), build_version

sys.path.insert(0, str(ROOT / 'Backend'))
from core.protocol import APP_BACKEND_VERSION

assert APP_BACKEND_VERSION == version

fixture = (ROOT / 'ContractFixtures/host_protocol_v6.json').read_text(encoding='utf-8')

# CI's release identity step (Info.plist SemVer and positive-integer build,
# checkout source identity) is executed in test_ci_workflow_contract.py.

# Protocol fixtures describe wire shape and use a placeholder for product
# release identity. The live backend resolves that value from the product SemVer.
assert '__PRODUCT_VERSION__' in fixture
assert '"backendVersion": "0.1"' not in fixture

# Single source of truth for Python version across CI workflows and runtime manifest.
python_runtime_version = json.loads((ROOT / 'Tools/python_runtime.json').read_text(encoding='utf-8'))['version']
dot_python_version = (ROOT / '.python-version').read_text(encoding='utf-8').strip()
assert dot_python_version == python_runtime_version, (dot_python_version, python_runtime_version)

pyproject_text = (ROOT / 'pyproject.toml').read_text(encoding='utf-8')
if tomllib is not None:
    pyproject = tomllib.loads(pyproject_text)
    ruff_target = pyproject['tool']['ruff']['target-version']
    mypy_version = pyproject['tool']['mypy']['python_version']
else:
    ruff_target = re.search(r'^target-version\s*=\s*"([^"]+)"', pyproject_text, re.M).group(1)
    mypy_version = re.search(r'^python_version\s*=\s*"([^"]+)"', pyproject_text, re.M).group(1)
assert ruff_target == 'py39', ruff_target
assert mypy_version == '3.10', mypy_version

print('product_version_contract_ok')
