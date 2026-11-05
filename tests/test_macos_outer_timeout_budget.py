"""macOS outer fixture budgets scale only when the CI runner profile opts in."""
import os
from pathlib import Path
from unittest.mock import patch

from macos_test_budget import scaled_outer_timeout


with patch.dict(os.environ, {}, clear=True):
    assert scaled_outer_timeout(40) == 40
with patch.dict(os.environ, {"MGT_MACOS_OUTER_TIMEOUT_SCALE": "2.0"}, clear=True):
    assert scaled_outer_timeout(40) == 80
    assert scaled_outer_timeout(65) == 130
for invalid in ("0.9", "2.1", "bogus"):
    with patch.dict(os.environ, {"MGT_MACOS_OUTER_TIMEOUT_SCALE": invalid}, clear=True):
        try:
            scaled_outer_timeout(40)
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid timeout scale accepted: {invalid}")

runtime_text_edit = Path(__file__).with_name("test_runtime_text_edit_completion.py").read_text()
assert "from macos_test_budget import scaled_outer_timeout" in runtime_text_edit
assert "timeout=scaled_outer_timeout(60)" in runtime_text_edit
assert "capture_output=True, text=True, timeout=60" not in runtime_text_edit

real_navigation = Path(__file__).with_name("real_module_navigation_harness.py").read_text()
assert "base_outer_timeout = 30 if startup_only else 45" in real_navigation
assert "timeout=scaled_outer_timeout(base_outer_timeout)" in real_navigation
assert "RunLoop.current.run(until:" in real_navigation
assert "NSApp.nextEvent(matching: .any" not in real_navigation

runtime_text_edit = Path(__file__).with_name("test_runtime_text_edit_completion.py").read_text()
assert "func runRuntimeTextEditJourney() throws" in runtime_text_edit
assert 'check(NSApp.isRunning,"runtime text-edit fixture did not enter the AppKit application event loop")' in runtime_text_edit
assert "app.run()" in runtime_text_edit

native_picker = Path(__file__).with_name("native_picker_harness.py").read_text()
assert "if case .accessibility = opening" in native_picker
assert "accessibility picker selection requires the AppKit application event loop" in native_picker

disclosure = Path(__file__).with_name("disclosure_ui_harness.py").read_text()
assert "let retirementDeadline = Date().addingTimeInterval(1)" in disclosure
assert "while Date() < retirementDeadline" in disclosure
assert "if settled { break }" in disclosure
assert "disclosureLifetimePump(0.01)" in disclosure
assert "disclosureLifetimePump(0.03)" not in disclosure

print("macos_outer_timeout_budget_ok")
