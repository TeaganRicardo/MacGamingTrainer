"""Hades II named encounter one-shot commits only at native RecordEncounter."""
import subprocess
import tempfile
from pathlib import Path

from lua_runtime_support import RESIDENT_DISPATCH_CONTRACT, require_lua52

ROOT = Path(__file__).resolve().parents[1]
LUA = require_lua52("Hades II named encounter native commit")
BASE = (
    ROOT / "tests/fixtures/hades2/gathering_room_model.lua"
).read_text(encoding="utf-8").split("local nativeCreate = CreateRoom")[0]
MODEL = (
    ROOT / "tests/fixtures/hades2/occurrence_routing_model.lua"
).read_text(encoding="utf-8")

scenario = r"""
setRoomSet("F")
CurrentRun.CurrentRoom.LegalEncounters = { "CombatNormal", "NemesisCombatF" }
setOccurrence("npc:Nemesis", "record-commit")

local selected = ChooseEncounter(CurrentRun, CurrentRun.CurrentRoom)
assert(selected.Name == "NemesisCombatF", "requested eligible encounter was not selected")
assert(M.nextOccurrenceTarget == "npc:Nemesis"
    and M.nextOccurrenceToken == "record-commit"
    and M.lastConsumedNextOccurrenceToken == nil,
  "ChooseEncounter consumed the one-shot before the native occurrence record")

RecordEncounter(CurrentRun, { Name = "CombatNormal" })
assert(M.nextOccurrenceTarget == "npc:Nemesis"
    and M.lastConsumedNextOccurrenceToken == nil,
  "an unrelated native encounter record consumed the pending target")

RecordEncounter(CurrentRun, selected)
assert(CurrentRun.EncountersOccurredCache.NemesisCombatF == 1,
  "fixture did not execute the native occurrence record")
assert(M.nextOccurrenceTarget == nil and M.nextOccurrenceToken == nil
    and M.lastConsumedNextOccurrenceToken == "record-commit",
  "matching native RecordEncounter did not consume the exact request")

-- Cancellation after selection but before native recording must remain authoritative.
setOccurrence("npc:Nemesis", "cancel-before-record")
local cancelled = ChooseEncounter(CurrentRun, CurrentRun.CurrentRoom)
assert(cancelled.Name == "NemesisCombatF"
    and M.nextOccurrenceTarget == "npc:Nemesis"
    and M.lastConsumedNextOccurrenceToken == "record-commit")
M.dispatch("cancel_world_occurrence", {
  leaseToken = M.nextOccurrenceToken,
  requestId = "cancel-before-record-action",
  includeCatalogs = false,
})
RecordEncounter(CurrentRun, cancelled)
assert(M.nextOccurrenceTarget == nil and M.nextOccurrenceToken == nil
    and M.lastConsumedNextOccurrenceToken == "record-commit",
  "recording an encounter after explicit cancellation synthesized a receipt")

print("hades2_occurrence_record_commit_ok")
"""

with tempfile.TemporaryDirectory(prefix="mgt-occurrence-record-") as directory:
    script = Path(directory) / "occurrence_record_commit.lua"
    script.write_text(BASE + MODEL + scenario, encoding="utf-8")
    result = subprocess.run(
        [
            LUA, str(script),
            str(ROOT / "Backend/games/hades2/runtime/hades.lua"),
            str(RESIDENT_DISPATCH_CONTRACT),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "hades2_occurrence_record_commit_ok" in result.stdout

print("hades2_occurrence_record_commit_ok")
