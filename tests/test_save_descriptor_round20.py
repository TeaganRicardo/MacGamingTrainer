from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix="mgt-save-descriptor-") as td:
    output = Path(td) / "binding.swift"
    subprocess.run([
        "python3", str(ROOT / "Tools/generate_game_binding.py"), "hades2", str(output)
    ], check=True, cwd=ROOT)
    generated = output.read_text(encoding="utf-8")
    assert "supportsSaveManagement: true" in generated

descriptor = (ROOT / "Sources/Core/Host/TrainerGameModule.swift").read_text(encoding="utf-8")
assert "let supportsSaveManagement: Bool = false" in descriptor

print("save_descriptor_round20_ok")
