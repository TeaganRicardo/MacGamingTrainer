import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "Tools/generate_hades2_command_binding.py"
CHECKED_IN = ROOT / "Sources/Hades2/Generated/Hades2Command.generated.swift"

with tempfile.TemporaryDirectory(prefix="mgt-hades-command-binding-") as td:
    generated = Path(td) / "Hades2Command.generated.swift"
    subprocess.run(
        [sys.executable, str(GENERATOR), str(generated)],
        check=True,
        cwd=ROOT,
    )
    assert generated.read_bytes() == CHECKED_IN.read_bytes(), (
        "checked-in Hades Host command metadata drifted from command_contract.py"
    )

print("hades2_command_binding_ok")
