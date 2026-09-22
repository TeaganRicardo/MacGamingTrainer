from pathlib import Path
import plistlib
import re
import sys

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
workflow = (ROOT / '.github/workflows/build2-macos.yml').read_text(encoding='utf-8')
fixture = (ROOT / 'ContractFixtures/host_protocol_v5.json').read_text(encoding='utf-8')

# Policy documents describe rules, not a second copy of current release values.
for stale in ('Current product version:', 'Current development build:', 'Latest released build:'):
    assert stale not in versioning
assert 'Game module contract — 0.1 baseline' not in modules

# CI derives both release identities from Info.plist and keeps their meanings
# distinct: SemVer for the product, positive integer for the bundle build.
assert "Print :CFBundleShortVersionString' Info.plist" in workflow
assert "Print :CFBundleVersion' Info.plist" in workflow
assert '[[ "$source_build" =~ ^[1-9][0-9]*$ ]]' in workflow
assert 'echo "build=$source_build"' in workflow
assert 'test "$version" = "$expected_version"' in workflow
assert 'test "$build" = "$expected_build"' in workflow
assert 'test "$source_version" = "$source_build"' not in workflow
assert "github.event.pull_request.head.sha" in workflow
assert 'source_sha=' in workflow
assert '-b${{ steps.version.outputs.build }}-' in workflow
assert 'MacGamingTrainer-0.1-build2' not in workflow
assert 'test "$version" = "0.1"' not in workflow
assert 'test "$build" = "2"' not in workflow

# Protocol fixtures describe wire shape and use a placeholder for product
# release identity. The live backend resolves that value from the product SemVer.
assert '__PRODUCT_VERSION__' in fixture
assert '"backendVersion": "0.1"' not in fixture

print('product_version_contract_ok')
