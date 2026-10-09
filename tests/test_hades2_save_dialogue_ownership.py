"""Native dialogue reset authority must not derive from a recorded boolean."""

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from games.hades2.save_document import LuaTable
from games.hades2.save_workspace import Hades2SaveWorkspace


SAFE = "HecatePostTrueEnding01"  # Native StoryResetData.TextLines target.
UNKNOWN = "UnverifiedScene"
MISSING = object()


def table(entries):
    return LuaTable(0, len(entries), entries)


def editor(*, gift=MISSING, choice=MISSING, run=None, lines=None):
    if lines is None:
        lines = [(SAFE, True), (UNKNOWN, True), ("GiftLine", True)]
    state_entries = [
        ("Resources", table([("MetaCurrency", 5.0)])),
        ("TextLinesRecord", table(lines)),
    ]
    if gift is not MISSING:
        state_entries.append(("GiftTextLinesOrderRecord", gift))
    if choice is not MISSING:
        state_entries.append(("TextLinesChoiceRecord", choice))
    root = table([
        ("GameState", table(state_entries)),
        ("CurrentRun", run if run is not None else table([])),
    ])
    session = SimpleNamespace(
        relative_path="Profile1.sav",
        document=SimpleNamespace(lua_state=root),
    )
    return Hades2SaveWorkspace(session, "Profile1"), root


def records(model):
    return {row["rawId"]: row for row in model.query(domain="dialogue", limit=100)["items"]}


empty_gifts = table([("Hecate", table([]))])
choice_record = table([(SAFE, "ChoiceA"), (UNKNOWN, "UnknownChoice")])

# A recorded, source-unverified identity must not acquire write permissions.
unverified, root = editor(gift=empty_gifts, choice=choice_record)
assert UNKNOWN in records(unverified)
assert records(unverified)[UNKNOWN]["editable"] is False
try:
    unverified.stage("dialogue:" + UNKNOWN, "set", False)
except ValueError:
    pass
else:
    raise AssertionError("unknown dialogue identifier became writable")
assert unverified.review()["changes"] == []
assert root["GameState"]["TextLinesRecord"][UNKNOWN] is True

# Missing, malformed, and partially malformed gift history must not serve as
# negative evidence that a source-verified dialogue is unrelated to gifting.
for provenance in (
    MISSING,
    "not a table",
    table([("Hecate", "not a per-character history table")]),
    table([("Hecate", table([(1.0, 3.0)]))]),
):
    unsafe, _ = editor(gift=provenance, choice=choice_record)
    assert records(unsafe)[SAFE]["editable"] is False
    try:
        unsafe.stage("dialogue:" + SAFE, "set", False)
    except ValueError:
        pass
    else:
        raise AssertionError("malformed gift provenance enabled a dialogue reset")

# A native-authored reset target remains visible but not writable when already
# accounted for in the gift-history array.
gifted = table([("Hecate", table([(1.0, SAFE)]))])
blocked, _ = editor(gift=gifted, choice=choice_record)
assert records(blocked)[SAFE]["editable"] is False

# The choice record is another native write owner, not an optional untyped
# ignore-if-malformed field.
for choices in (MISSING, "not a table", table([(SAFE, table([]))])):
    bad_choices, _ = editor(gift=empty_gifts, choice=choices)
    assert records(bad_choices)[SAFE]["editable"] is False

# A malformed current-run owner must never be silently ignored.
for bad_run in (
    table([("TextLinesRecord", "invalid")]),
    table([("TextLinesChoiceRecord", table([(SAFE, table([]))]))]),
    table([("CurrentRoom", table([("TextLinesRecord", "invalid")]))]),
):
    denied, _ = editor(gift=empty_gifts, choice=choice_record, run=bad_run)
    assert records(denied)[SAFE]["editable"] is False

# CurrentRun records are also written by PlayTextLine and must be accounted
# for in an authorized reset; no stale per-run replay gate can remain unseen.
run = table([
    ("TextLinesRecord", table([(SAFE, True)])),
    ("HubTextLinesRecord", table([(SAFE, True)])),
    ("TextLinesChoiceRecord", table([(SAFE, "ChoiceA")])),
    ("CurrentRoom", table([("TextLinesRecord", table([(SAFE, True)]))])),
])
legitimate, root = editor(gift=empty_gifts, choice=choice_record, run=run)
assert records(legitimate)[SAFE]["editable"] is True
legitimate.stage("dialogue:" + SAFE, "set", False)
linked = {change["id"] for change in legitimate.review()["changes"] if change["id"].startswith("linked:")}
assert "linked:dialogue:" + SAFE in linked
for owner in ("TextLinesRecord", "HubTextLinesRecord", "TextLinesChoiceRecord", "CurrentRoom.TextLinesRecord"):
    assert "linked:dialogue:CurrentRun." + owner + ":" + SAFE in linked

# A rejected dialogue stage cannot leave a pending intent or mutate unrelated
# resources, even when it follows a valid cross-domain resource stage.
legitimate.stage("resource:MetaCurrency", "set", 22)
try:
    legitimate.stage("dialogue:" + UNKNOWN, "set", False)
except ValueError:
    pass
else:
    raise AssertionError("unverified cross-domain edit was staged")
assert {row["id"] for row in legitimate.review()["changes"] if not row["id"].startswith("linked:")} == {
    "dialogue:" + SAFE, "resource:MetaCurrency"
}
assert root["GameState"]["Resources"]["MetaCurrency"] == 5.0

print("hades2_save_dialogue_ownership_ok")
