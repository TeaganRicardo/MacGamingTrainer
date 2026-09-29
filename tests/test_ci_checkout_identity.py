"""CI scope and executable checkout must refer to the same intended commit."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for name in ('linux-contracts.yml', 'build2-macos.yml', 'module-build-matrix.yml'):
    workflow = (ROOT / '.github/workflows' / name).read_text()
    steps = re.split(r'(?m)^      - ', workflow)[1:]
    checkouts = 0
    for index, step in enumerate(steps):
        if not re.search(r'uses: actions/checkout@', step):
            continue
        checkouts += 1
        assert re.search(r'(?m)^          ref: \$\{\{ env\.HEAD_SHA \}\}\s*$', step), name
        assert 'fetch-depth: 0' in step, name
        following = steps[index + 1]
        assert 'git rev-parse HEAD' in following and '"$HEAD_SHA"' in following, name
        # A gated checkout must not leave an unconditional assertion on the
        # documentation fast path, which intentionally has no build checkout.
        conditions = re.findall(r'(?m)^        if: (.+)$', step)
        assert not conditions or f'if: {conditions[0]}' in following, name
    assert checkouts, name
print('ci_checkout_identity_ok')
