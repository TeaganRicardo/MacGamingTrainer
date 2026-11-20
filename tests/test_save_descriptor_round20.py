import re
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix="mgt-save-descriptor-") as td:
    subprocess.run([
        "python3", str(ROOT / "Tools/generate_game_binding.py"), "hades2", "--module-sources", td
    ], check=True, cwd=ROOT)
    generated = (Path(td) / "Hades2/GameBinding.generated.swift").read_text(encoding="utf-8")
    assert "supportsSaveManagement: true" in generated

descriptor = (ROOT / "Sources/Core/Host/TrainerGameModule.swift").read_text(encoding="utf-8")
# Kept (lint): GameModuleDescriptor requires an explicit supportsSaveManagement argument;
# adding a default compiles with existing callers.
assert not re.search(r"supportsSaveManagement:\s*Bool\s*=", descriptor)

print("save_descriptor_round20_ok")
