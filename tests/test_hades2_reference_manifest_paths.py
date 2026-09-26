import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "docs/reference/hades2/1.139672-24556151"
manifest = json.loads((SNAPSHOT / "manifest.json").read_text(encoding="utf-8"))

for relative_path, expected_rows in manifest["outputs"].items():
    path = SNAPSHOT / relative_path
    assert path.is_file(), f"manifest output is not a usable snapshot-relative path: {relative_path}"
    with path.open(newline="", encoding="utf-8") as stream:
        actual_rows = sum(1 for _ in csv.reader(stream)) - 1
    assert actual_rows == expected_rows, (relative_path, expected_rows, actual_rows)

print("hades2_reference_manifest_paths_ok")
