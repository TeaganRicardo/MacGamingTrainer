import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Historical test files using these tokens are intentionally grandfathered.
# This gate examines only files ADDED by the current change, so it does not
# encode or maintain an allowlist of the old names.
EPOCH_TOKEN = re.compile(r"(?:^|_)(?:round\d+|v0\d+)(?:_|\.py$)")


def changed_added_tests(base: str, head: str) -> list[str]:
    merge_base = subprocess.check_output(
        ["git", "merge-base", base, head],
        cwd=ROOT,
        text=True,
    ).strip()
    output = subprocess.check_output(
        ["git", "diff", "--no-renames", "--name-status", merge_base, head, "--", "tests"],
        cwd=ROOT,
        text=True,
    )
    added = []
    for raw in output.splitlines():
        status, *paths = raw.split("\t")
        if status == "A" and paths and paths[0].startswith("tests/test_") and paths[0].endswith(".py"):
            added.append(paths[0])
    return added


base = os.environ.get("BASE_SHA", "")
head = os.environ.get("HEAD_SHA", "")
if base and head and set(base) != {"0"}:
    for path in changed_added_tests(base, head):
        name = Path(path).name
        assert not EPOCH_TOKEN.search(name), (
            f"new test file uses a historical epoch token: {path}; "
            "use a descriptive test_<subject>.py name and keep chronology in comments"
        )

print("test_filename_governance_ok")
