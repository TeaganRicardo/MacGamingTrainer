"""Save Editor physical Lua owner identity is unique before semantic access.

Only synthetic document trees are used; this test never accesses user save paths.
"""
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from games.hades2.save_document import LuaTable
from games.hades2.save_workspace import Hades2SaveWorkspace


def table(entries):
    return LuaTable(0, len(entries), entries)


def editor(game_state):
    root = table([("GameState", game_state), ("CurrentRun", table([]))])
    session = SimpleNamespace(
        document=SimpleNamespace(lua_state=root),
        relative_path="Profile1.sav",
    )
    return Hades2SaveWorkspace(session, "Profile1"), root


def rejects(call, identity):
    try:
        call()
    except ValueError as error:
        assert "ambiguous" in str(error).lower(), (identity, str(error))
    else:
        raise AssertionError(identity + " resolved a duplicated physical Lua key")


# The lossless codec retains both entries, but a semantic read, set, or
# removal cannot silently pick only the first physical occurrence.
duplicates = table([
    ("MetaCurrency", 5.0), ("MetaCurrency", 99.0),
    ("SafeUnrelated", 7.0),
])
original = duplicates.entries()
rejects(lambda: duplicates["MetaCurrency"], "direct semantic read")
rejects(lambda: duplicates.__setitem__("MetaCurrency", 8.0), "direct semantic set")
rejects(lambda: duplicates.__delitem__("MetaCurrency"), "direct semantic remove")
assert duplicates.entries() == original
duplicates["SafeUnrelated"] = 8.0
assert duplicates["SafeUnrelated"] == 8.0
assert duplicates.entries()[:2] == original[:2], "an unrelated safe edit must not destroy unknown data"

# Lua numbers 1 and 1.0 alias, but Lua true and numeric 1 do not.
numeric = table([(1, "integer"), (1.0, "float"), (True, "boolean")])
rejects(lambda: numeric[1], "equivalent Lua numeric keys")
assert numeric[True] == "boolean"

# A duplicated game-state owner selector is just as ambiguous as a leaf.
a = table([("Resources", table([("MetaCurrency", 5.0)]))])
b = table([("Resources", table([("MetaCurrency", 99.0)]))])
root = table([("GameState", a), ("GameState", b)])
w = Hades2SaveWorkspace(
    SimpleNamespace(document=SimpleNamespace(lua_state=root), relative_path="Profile1.sav"),
    "Profile1",
)
rejects(lambda: w.stage("resource:MetaCurrency", "set", 10), "root GameState owner")

# Resource scalar and player-stat leaf collisions may not become staged edits.
w, root = editor(table([
    ("Resources", table([("MetaCurrency", 5.0), ("MetaCurrency", 99.0),
                         ("GiftPoints", 1.0)])),
    ("GameplayTime", 10.0), ("GameplayTime", 20.0),
]))
w.stage("resource:GiftPoints", "set", 2)
before = root.entries()
rejects(lambda: w.stage("resource:MetaCurrency", "set", 42), "resource leaf owner")
rejects(lambda: w.stage("playerStat:GameplayTime", "set", 300.0), "statistic leaf owner")
assert w.review()["count"] == 1
assert w.review()["changes"][0]["id"] == "resource:GiftPoints"
assert root.entries() == before

# A duplicated Flags table owner and duplicated NPC history entry must be
# rejected by the same semantic identity contract.
w, _ = editor(table([
    ("Resources", table([("MetaCurrency", 5.0)])),
    ("Flags", table([])), ("Flags", table([("HasPinnedAnyBoon", True)])),
]))
rejects(lambda: w.stage("flag:HasPinnedAnyBoon", "set", True), "duplicate flags owner")

w, _ = editor(table([
    ("Resources", table([("MetaCurrency", 5.0)])),
    ("NPCInteractions", table([
        ("NPC_Nemesis_01", 1.0), ("NPC_Nemesis_01", 8.0),
    ])),
]))
rejects(lambda: w.stage("interaction:NPC_Nemesis_01", "set", 4),
        "duplicate relationship counter")

# Linked progression/equipment owners also require unique identities; an
# invalid entry must not be hidden by a per-row malformed-data fallback.
w, _ = editor(table([
    ("QuestStatus", table([])),
    ("MetaUpgradeState", table([
        ("ChanneledCast", table([
            ("Unlocked", True), ("Level", 2.0), ("Level", 3.0),
        ])),
    ])),
]))
rejects(lambda: w.stage("card:ChanneledCast:Level", "set", 3),
        "duplicate Arcana level")

w, _ = editor(table([
    ("WeaponsUnlocked", table([
        ("WeaponDagger", True), ("WeaponDagger", False),
    ])),
    ("WorldUpgrades", table([])),
    ("WorldUpgradesAdded", table([])),
]))
rejects(lambda: w.stage("weapon:WeaponDagger", "set", False),
        "duplicate weapon ownership")

w, _ = editor(table([
    ("WeaponsUnlocked", table([])),
    ("WorldUpgrades", table([])),
    ("WorldUpgradesAdded", table([])),
    ("FamiliarsUnlocked", table([
        ("CatFamiliar", True), ("CatFamiliar", False),
    ])),
]))
rejects(lambda: w.stage("familiar:CatFamiliar", "set", False),
        "duplicate Familiar ownership")


# Advanced must preserve both physical rows with stable, distinct Swift IDs,
# including the same-type duplicated container keys. The second physical
# container must never silently navigate to the first one.
w, _ = editor(table([
    ("Resources", table([("MetaCurrency", 5.0), ("MetaCurrency", 99.0)])),
    ("Twice", table([("Name", "first")])),
    ("Twice", table([("Name", "second")])),
    ("Distinct", table([("Other", 1.0)])),
]))
leaf_rows = w.query(domain="advanced", path=["GameState", "Resources"])["items"]
assert len(leaf_rows) == 2
assert len({entry["id"] for entry in leaf_rows}) == 2
assert all(entry["pathAmbiguous"] for entry in leaf_rows)
assert w.query(domain="advanced", path=["GameState", "Resources"])["items"] == leaf_rows

container_rows = w.query(domain="advanced", path=["GameState"])["items"]
twice = [entry for entry in container_rows if entry["rawId"] == "Twice"]
assert len(twice) == 2 and len({entry["id"] for entry in twice}) == 2
assert all(entry["pathAmbiguous"] for entry in twice)
assert all(entry["childCount"] == 1 for entry in twice)
rejects(lambda: w.query(domain="advanced", path=["GameState", "Twice"]),
        "ambiguous Advanced drilldown")
assert w.query(domain="advanced", path=["GameState", "Distinct"])["total"] == 1
