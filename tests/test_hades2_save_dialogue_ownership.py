"""Native dialogue reset authority must not derive from a recorded boolean."""

import dataclasses
import struct
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from core.adapter import GameAdapterContext
from core.module_manifest import GameModuleManifest, SaveManagementSpec, SaveRootSpec
from core.protocol import JsonlRequestRouter
from games.hades2.adapter import Hades2Adapter
from games.hades2.save_document import Hades2SaveDocument, Hades2SaveHeader, LuaTable
from games.hades2 import save_narrative
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
    root = model.document.lua_state
    return {name: save_narrative.entry_row(root, "dialogueReset:" + name)
            for name in save_narrative.reset_decisions(root)}


empty_gifts = table([("Hecate", table([]))])
choice_record = table([(SAFE, "ChoiceA"), (UNKNOWN, "UnknownChoice")])

# A recorded, source-unverified identity must not acquire write permissions.
unverified, root = editor(gift=empty_gifts, choice=choice_record)
assert UNKNOWN in records(unverified)
assert records(unverified)[UNKNOWN]["editable"] is False
try:
    unverified.stage("dialogueReset:" + UNKNOWN, "set", False)
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
        unsafe.stage("dialogueReset:" + SAFE, "set", False)
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
legitimate.stage("dialogueReset:" + SAFE, "set", False)
linked = {change["id"] for change in legitimate.review()["changes"] if change["id"].startswith("linked:")}
assert "linked:dialogue:" + SAFE in linked
for owner in ("TextLinesRecord", "HubTextLinesRecord", "TextLinesChoiceRecord", "CurrentRoom.TextLinesRecord"):
    assert "linked:dialogue:CurrentRun." + owner + ":" + SAFE in linked

# A rejected dialogue stage cannot leave a pending intent or mutate unrelated
# resources, even when it follows a valid cross-domain resource stage.
legitimate.stage("resource:MetaCurrency", "set", 22)
try:
    legitimate.stage("dialogueReset:" + UNKNOWN, "set", False)
except ValueError:
    pass
else:
    raise AssertionError("unverified cross-domain edit was staged")
assert {row["id"] for row in legitimate.review()["changes"] if not row["id"].startswith("linked:")} == {
    "dialogueReset:" + SAFE, "resource:MetaCurrency"
}
assert root["GameState"]["Resources"]["MetaCurrency"] == 5.0

# Parseable duplicate-linked-owner cases must stay inspectable yet read-only.
# LuaTable deliberately preserves duplicate luabins entries, so first-key
# lookup/removal is not sufficient evidence for a standalone dialogue reset.
ambiguous_cases = (
    ("primary", {"lines": [(SAFE, True), (SAFE, True), (UNKNOWN, True)]}),
    ("choice", {"choice": table([(SAFE, "ChoiceA"), (SAFE, "ChoiceB")])}),
    ("current-run play", {"run": table([
        ("TextLinesRecord", table([(SAFE, True), (SAFE, False)])),
    ])}),
    ("current-run hub", {"run": table([
        ("HubTextLinesRecord", table([(SAFE, True), (SAFE, True)])),
    ])}),
    ("current-run choice", {"run": table([
        ("TextLinesChoiceRecord", table([(SAFE, "ChoiceA"), (SAFE, "ChoiceB")])),
    ])}),
    ("current-room play", {"run": table([
        ("CurrentRoom", table([
            ("TextLinesRecord", table([(SAFE, True), (SAFE, True)])),
        ])),
    ])}),
    ("duplicate current-run owner field", {"run": table([
        ("TextLinesRecord", table([(SAFE, True)])),
        ("TextLinesRecord", table([(SAFE, False)])),
    ])}),
    ("duplicate current-room owner field", {"run": table([
        ("CurrentRoom", table([
            ("TextLinesRecord", table([(SAFE, True)])),
            ("TextLinesRecord", table([(SAFE, False)])),
        ])),
    ])}),
    ("gift numeric index", {"gift": table([
        ("Hecate", table([(1.0, "AnotherLine"), (1, "SecondLine")])),
    ])}),
    ("gift character owner", {"gift": table([
        ("Hecate", table([])), ("Hecate", table([])),
    ])}),
)
for label, override in ambiguous_cases:
    context = {"gift": empty_gifts, "choice": choice_record, **override}
    unsafe, original_root = editor(**context)
    original_lines = original_root["GameState"]["TextLinesRecord"].entries()
    displayed = [
        row for row in records(unsafe).values() if row["rawId"] == SAFE
    ]
    assert len(displayed) == 1, (label, "duplicate semantic row IDs")
    assert displayed[0]["editable"] is False, label
    assert displayed[0]["mutationKinds"] == [], label
    try:
        unsafe.stage("dialogueReset:" + SAFE, "set", False)
    except ValueError:
        pass
    else:
        raise AssertionError("ambiguous dialogue reset was staged: " + label)
    assert unsafe.review()["changes"] == [], label
    assert original_root["GameState"]["TextLinesRecord"].entries() == original_lines, label
    # An unrelated valid intent cannot silently authorize the rejected dialogue.
    unsafe.stage("resource:MetaCurrency", "set", 22)
    assert [change["id"] for change in unsafe.review()["changes"]] == [
        "resource:MetaCurrency"
    ], label

# An owner field name duplicated inside GameState also makes its first-match
# choice record ambiguous, even when each nested table is individually valid.
unsafe, original_root = editor(gift=empty_gifts, choice=choice_record)
game = original_root["GameState"]
original_root["GameState"] = table([
    *game.entries(), ("TextLinesChoiceRecord", table([(SAFE, "ChoiceB")]))
])
row = records(unsafe)[SAFE]
assert row["editable"] is False
try:
    unsafe.stage("dialogueReset:" + SAFE, "set", False)
except ValueError:
    pass
else:
    raise AssertionError("ambiguous GameState dialogue owner was staged")

# #821: DialogueWriteBlocked retains its specific error code (e.g. notResettable)
# across JsonlRequestRouter rather than being flattened to invalid_request.
with tempfile.TemporaryDirectory(prefix="mgt-821-dialogue-code-") as tmp:
    temp_root = Path(tmp)
    saves = temp_root / "saves"
    saves.mkdir(parents=True)
    profile = b"Profile1"
    (saves / "activeProfile").write_bytes(b"SGB1" + struct.pack("<I", len(profile)) + profile)
    doc_root = table([
        ("GameState", table([
            ("Resources", table([("MetaCurrency", 5.0)])),
            ("GameplayTime", 10.0),
            ("TotalTime", 20.0),
            ("TextLinesRecord", table([(SAFE, True), (UNKNOWN, True)])),
            ("GiftTextLinesOrderRecord", empty_gifts),
            ("TextLinesChoiceRecord", choice_record),
        ])),
        ("CurrentRun", table([])),
    ])
    header = Hades2SaveHeader(
        game_version=0x12,
        save_flags=0,
        timestamp=100,
        location="Crossroads",
        completed_runs=1,
        accumulated_meta_points=0,
        active_shrine_points=0,
        meta_upgrade_level=0,
        cosmetics_points=0,
        easy_mode=0,
        hard_mode=0,
        notable_lua_data=("GameState", "CurrentRun"),
        map_name="Hub_Main",
        next_map_name="F_Opening01",
    )
    (saves / "Profile1.sav").write_bytes(Hades2SaveDocument(header, [doc_root]).to_bytes())
    manifest = GameModuleManifest.load(ROOT / "Backend/games/hades2/module.json")
    spec = SaveManagementSpec(
        roots=(SaveRootSpec("main", str(saves), ("Profile*.sav", "activeProfile")),),
        provider="games.hades2.save_provider:Hades2SaveProvider",
        hot_backup=True,
        restore_policy="hotPreferred",
        staged_restore=True,
    )
    context = dataclasses.replace(
        GameAdapterContext.from_manifest(manifest, home=temp_root / "home"),
        save_management=spec,
    )
    stub_session = SimpleNamespace(
        pid=None,
        pending_resume_pid=None,
        cleanup_pending=False,
        alive=lambda: False,
        close=lambda: None,
        invalidate_generation=lambda: None,
    )
    adapter = Hades2Adapter(
        context=context,
        resident_session=stub_session,
        time_warp_controller=object(),
        game_path=temp_root / "AbsentHades2.app",
    )
    router = JsonlRequestRouter(
        adapter,
        save_data_root=temp_root / "router-data",
        target_running_probe=lambda: False,
    )
    try:
        opened = router.handle({"id": "open-1", "command": "save_editor_open", "params": {"language": "en"}})
        assert opened["ok"] is True, opened
        ws_id = opened["result"]["workspaceId"]
        gen = opened["result"]["baselineGeneration"]
        blocked_reply = router.handle({
            "id": "stage-blocked-dialogue",
            "command": "save_editor_stage",
            "params": {
                "workspaceId": ws_id,
                "baselineGeneration": gen,
                "entryId": "dialogueReset:" + UNKNOWN,
                "operation": "set",
                "value": False,
                "language": "en",
            },
        })
        assert blocked_reply["ok"] is False, blocked_reply
        assert blocked_reply["error"]["code"] == "notResettable", blocked_reply
    finally:
        router.close()

print("hades2_save_dialogue_ownership_ok")
