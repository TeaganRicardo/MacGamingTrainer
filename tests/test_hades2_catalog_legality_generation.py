import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "Tools/generate_hades2_catalog_legality.py"


result = subprocess.run(
    [sys.executable, str(GENERATOR), "--check"],
    cwd=ROOT,
    text=True,
    capture_output=True,
)
assert result.returncode == 0, result.stdout + result.stderr

print("hades2_catalog_legality_generation_ok")
