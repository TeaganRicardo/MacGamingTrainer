import ast
import re
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON_SCHEMA = ROOT / "Backend/games/hades2/schema.py"
SWIFT_MODEL = ROOT / "Sources/Hades2/Hades2Model.swift"


def _python_stat_ranges():
    tree = ast.parse(PYTHON_SCHEMA.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "STAT_RULES"
            for target in node.targets
        ):
            rules = ast.literal_eval(node.value)
            return {
                key: (Decimal(str(rule["min"])), Decimal(str(rule["max"])))
                for key, rule in rules.items()
            }
    raise AssertionError("schema.py does not define STAT_RULES")


def _swift_stat_ranges():
    source = SWIFT_MODEL.read_text(encoding="utf-8")
    declaration = re.search(
        r"private\s+static\s+let\s+statRules\s*:\s*\[String:\s*StatRule\]\s*=\s*\[(.*?)\n\s*\]",
        source,
        re.DOTALL,
    )
    assert declaration is not None, "Hades2Model.swift does not define statRules"

    ranges = {}
    entry_pattern = re.compile(
        r'"([^"]+)"\s*:\s*\.init\(min:\s*([-+\d.]+),\s*max:\s*([-+\d.]+),\s*integer:\s*(?:true|false)\)'
    )
    for key, minimum, maximum in entry_pattern.findall(declaration.group(1)):
        assert key not in ranges, f"duplicate Swift stat rule: {key}"
        ranges[key] = (Decimal(minimum), Decimal(maximum))

    entries = [line for line in declaration.group(1).splitlines() if line.strip()]
    entry_lines = [line for line in entries if '"' in line and ".init(" in line]
    assert len(entry_lines) == len(entries), "could not parse every Swift stat rule"
    assert len(ranges) == len(entries), "could not parse every Swift stat rule"
    return ranges


def test_python_and_swift_hades2_stat_keys_and_ranges_match():
    python_ranges = _python_stat_ranges()
    swift_ranges = _swift_stat_ranges()

    assert set(swift_ranges) == set(python_ranges), (
        f"stat keys differ: Python-only={sorted(set(python_ranges) - set(swift_ranges))}, "
        f"Swift-only={sorted(set(swift_ranges) - set(python_ranges))}"
    )
    assert swift_ranges == python_ranges, (
        "stat ranges differ: "
        f"{ {key: (python_ranges[key], swift_ranges[key]) for key in python_ranges if python_ranges[key] != swift_ranges[key]} }"
    )


if __name__ == "__main__":
    test_python_and_swift_hades2_stat_keys_and_ranges_match()
