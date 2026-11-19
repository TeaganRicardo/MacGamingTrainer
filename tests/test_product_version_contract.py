import plistlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
plist = plistlib.loads((ROOT / 'Info.plist').read_bytes())
version = plist['CFBundleShortVersionString']
build_version = plist['CFBundleVersion']

assert re.fullmatch(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)', version), version
assert re.fullmatch(r'[1-9][0-9]*', build_version), build_version

sys.path.insert(0, str(ROOT / 'Backend'))
from core.protocol import APP_BACKEND_VERSION

assert APP_BACKEND_VERSION == version

versioning = (ROOT / 'VERSIONING.md').read_text(encoding='utf-8')
modules = (ROOT / 'GAME_MODULES.md').read_text(encoding='utf-8')
fixture = (ROOT / 'ContractFixtures/host_protocol_v6.json').read_text(encoding='utf-8')

# Policy documents describe rules, not a second copy of current release values.
for stale in ('Current product version:', 'Current development build:', 'Latest released build:'):
    assert stale not in versioning
assert 'Game module contract — 0.1 baseline' not in modules

# CI's release identity step (Info.plist SemVer and positive-integer build,
# checkout source identity) is executed in test_ci_workflow_contract.py.

# Protocol fixtures describe wire shape and use a placeholder for product
# release identity. The live backend resolves that value from the product SemVer.
assert '__PRODUCT_VERSION__' in fixture
assert '"backendVersion": "0.1"' not in fixture

print('product_version_contract_ok')
