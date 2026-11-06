"""A native fixture must not touch the user's real preference tree.

Phase C of #670. A bare executable's `UserDefaults.standard` resolves to a
domain named after the process, and `CFFIXED_USER_HOME` does not redirect it on
current macOS. Isolation therefore has to come from injecting a memory-backed
`UserDefaults`; neither the environment nor deleting a global domain before the
run can make repeated or concurrent runs start from the same state.
"""
from pathlib import Path

TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parent


def calls(source: str, opener: str) -> list[str]:
    """Return each call's argument text, using balanced parentheses."""
    found = []
    start = 0
    while True:
        index = source.find(opener, start)
        if index < 0:
            return found
        depth = 0
        for position in range(index + len(opener) - 1, len(source)):
            if source[position] == "(":
                depth += 1
            elif source[position] == ")":
                depth -= 1
                if depth == 0:
                    found.append(source[index:position + 1])
                    start = position + 1
                    break
        else:
            return found


# A fixture that deletes a preference domain mutates the user's tree, races
# with any concurrent run of the same fixture, and hides a missing injection.
# This contract is the only file allowed to name the retired mechanism.
for path in sorted(TESTS.glob("*.py")):
    if path.name == Path(__file__).name:
        continue
    text = path.read_text(encoding="utf-8")
    assert '"/usr/bin/defaults"' not in text, (
        f"{path.name}: a fixture must not mutate a global preference domain"
    )
    assert "defaults delete" not in text, (
        f"{path.name}: a fixture must not mutate a global preference domain"
    )

view_state = (TESTS / "test_hades2_view_state_flow.py").read_text(encoding="utf-8")

# Every store that would otherwise reach cfprefsd is given memory-backed
# defaults. The model's own default is `.standard`, so an omission here is a
# real leak, not a style issue.
models = calls(view_state, "Hades2TrainerModel(")
assert len(models) == 5, f"expected five model constructions, found {len(models)}"
for call in models:
    assert "shortcutDefaults: InMemoryDefaults()" in call, call

localizations = calls(view_state, "TrainerLocalizationStore(")
assert localizations, "the fixture no longer constructs a localization store"
for call in localizations:
    assert "defaults:" in call, call
assert "let localizationDefaults = InMemoryDefaults()" in view_state

# The environment is still scoped for the other CF consumers; it is simply not
# the mechanism the preference stores rely on.
assert view_state.count('env["CFFIXED_USER_HOME"] = str(home)') == 2

# The test double has to override every accessor the stores use, or a write
# would fall through to the real suite.
double = (TESTS / "fixtures/swift/InMemoryDefaults.swift").read_text(encoding="utf-8")
for accessor in (
    "override func object(forKey defaultName: String) -> Any?",
    "override func string(forKey defaultName: String) -> String?",
    "override func set(_ value: Any?, forKey defaultName: String)",
    "override func removeObject(forKey defaultName: String)",
):
    assert accessor in double, accessor

print("macos_fixture_preference_isolation_ok")
