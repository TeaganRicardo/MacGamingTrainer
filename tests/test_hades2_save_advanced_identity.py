"""Advanced save tree identity must preserve Lua key types and path boundaries."""

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from games.hades2.save_document import Hades2SaveDocument, Hades2SaveHeader, LuaTable
from games.hades2.save_workspace import Hades2SaveWorkspace


def table(entries):
    return LuaTable(0, len(entries), entries)


root = table([
    ("GameState", table([
        ("MixedKeys", table([
            (1.0, "numeric"),
            ("1.0", "text"),
            (True, "boolean"),
            ("True", "textual boolean"),
        ])),
        ("a/b", table([("c", "first")])),
        ("a", table([("b/c", "second")])),
    ])),
])
session = SimpleNamespace(
    document=Hades2SaveDocument(
        Hades2SaveHeader(0x12, 0, 123, "Crossroads", 1, 2, 3, 4, 5, 0, 0,
                        ("GameState", "CurrentRun"), "Hub_Main", "F_Opening01"),
        [root],
    ),
    relative_path="Profile1.sav",
)
workspace = Hades2SaveWorkspace(session, profile="Profile1")

siblings = workspace.query(domain="advanced", path=["GameState", "MixedKeys"])
assert siblings["total"] == 4
assert len({row["id"] for row in siblings["items"]}) == 4, (
    "Lua numeric, string and boolean keys must not share a Swift list identity"
)
assert {type(row["path"][-1]) for row in siblings["items"]} == {
    float, str, bool
}
assert all(row["editable"] and "set" in row["mutationKinds"] for row in siblings["items"])

slash_first = workspace.query(
    domain="advanced", path=["GameState", "a/b"]
)["items"][0]
slash_second = workspace.query(
    domain="advanced", path=["GameState", "a"]
)["items"][0]
assert slash_first["path"] == ["GameState", "a/b", "c"]
assert slash_second["path"] == ["GameState", "a", "b/c"]
assert slash_first["id"] != slash_second["id"], (
    "path delimiter characters must not alias different tree nodes"
)
assert workspace.query(
    domain="advanced", path=["GameState", "MixedKeys"]
)["items"] == siblings["items"], "identities must remain stable across paging/query"

# Each typed identity also owns an independent writable path. Exercise the
# basket and real codec so Lua's true/1/string distinctions protect writes as
# well as Swift list identity.
for index, row in enumerate(siblings["items"]):
    workspace.stage(row["id"], "set", "changed " + str(index))
assert workspace.review()["actionCount"] == 4
candidate = workspace._validated_review_state(workspace._pending.values())
reopened = Hades2SaveDocument.from_bytes(candidate.to_bytes()).lua_state
mixed = reopened["GameState"]["MixedKeys"]
assert [mixed[row["path"][-1]] for row in siblings["items"]] == [
    "changed " + str(index) for index in range(4)
]
assert reopened["GameState"]["a/b"]["c"] == "first"
assert reopened["GameState"]["a"]["b/c"] == "second"
