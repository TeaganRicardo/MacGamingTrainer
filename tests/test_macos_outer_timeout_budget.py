"""macOS outer fixture budgets scale only when the CI runner profile opts in."""
import os
from unittest.mock import patch

from macos_test_budget import scaled_outer_timeout


with patch.dict(os.environ, {}, clear=True):
    assert scaled_outer_timeout(40) == 40
with patch.dict(os.environ, {"MGT_MACOS_OUTER_TIMEOUT_SCALE": "1.5"}, clear=True):
    assert scaled_outer_timeout(40) == 60
    assert scaled_outer_timeout(65) == 97.5
for invalid in ("0.9", "2.1", "bogus"):
    with patch.dict(os.environ, {"MGT_MACOS_OUTER_TIMEOUT_SCALE": invalid}, clear=True):
        try:
            scaled_outer_timeout(40)
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid timeout scale accepted: {invalid}")

print("macos_outer_timeout_budget_ok")
