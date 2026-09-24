import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
production_swift = sorted((ROOT / "Sources").rglob("*.swift"))
fixture_swift = sorted((ROOT / "ContractFixtures/reference_module/frontend").rglob("*.swift"))

constructor = re.compile(r"\bTrainerBackendSession\s*\(")
calls = []
for path in production_swift + fixture_swift:
    text = path.read_text(encoding="utf-8")
    for match in constructor.finditer(text):
        calls.append((
            str(path.relative_to(ROOT)),
            text.count("\n", 0, match.start()) + 1,
        ))

owners = [path for path, _line in calls]
assert owners == ["Sources/App.swift"], (
    "TrainerBackendSession construction must have exactly one App owner; "
    f"found {calls}"
)

print("host_module_session_ownership_ok")
