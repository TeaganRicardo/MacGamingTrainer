"""Keep the Hades II Save Editor native process guard on the shared macOS runner budget."""
from pathlib import Path

source = Path(__file__).with_name("test_hades2_save_editor_frontend.py").read_text()
assert "from macos_test_budget import scaled_outer_timeout" in source
assert "timeout=scaled_outer_timeout(30)" in source
assert "timeout=30," not in source

print("hades2_save_editor_frontend_budget_ok")
