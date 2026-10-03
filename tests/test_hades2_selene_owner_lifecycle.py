from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
LUA = (ROOT / "Backend/games/hades2/runtime/hades.lua").read_text(encoding="utf-8")
STATUS = (ROOT / "PROJECT_STATUS.md").read_text(encoding="utf-8")


def block(start: str, end: str) -> str:
    left = LUA.index(start)
    right = LUA.index(end, left)
    return LUA[left:right]


def test_selene_exact_catalog_is_owner_backed():
    rewards = block("local function rewards()", "local statOrder, statRegistry")

    assert 'acquisitionMode = "seleneSpell"' in rewards
    assert 'acquisitionMode = "seleneTalent"' in rewards
    assert 'type(SpellData) == "table"' in rewards
    assert "spellData.Skip" in rewards

    # Exact talent rows are projected from the current generated Path of Stars,
    # never from every *Talent record in TraitData.
    assert "seleneModel.currentSpell()" in rewards
    assert "slotted.Talents" in rewards
    assert "selene:talent:" in rewards
    assert "for traitName in pairs(TraitData)" not in rewards


def test_selene_mutation_owns_spell_and_tree_lifecycle():
    dispatch = block('if command == "set_trait_level"', 'if command == "open_sell_traits"')

    assert "local seleneModel = (function()" in LUA

    for token in (
        "teardownSlottedSpell",
        "applySeleneSpell",
        "applySeleneTalent",
        "UpdateTalentPointInvestedCache",
        "UnequipWeapon",
    ):
        assert token in LUA, token

    # Talent level/rarity/removal must synchronize both mounted TraitData and
    # the owning SlottedSpell.Talents nodes.
    assert "seleneTalentNodes" in LUA
    assert "family == \"hexTalent\"" in dispatch
    assert "syncSeleneTalent" in LUA


def test_selene_current_run_capabilities_are_typed():
    family = block("local function traitFamily", "local function availableRarities")
    capabilities = block("local function operationCapabilities", "local currentRunTraits = function()")

    assert 'return "hexTalent"' in family
    assert 'family == "hex"' in capabilities
    assert 'family == "hexTalent"' in capabilities

    # #237 is no longer a deferred owner family once the slice is implemented.
    deferred = block("local deferredTraitIssues", "local rarityOrder")
    assert "hex = 237" not in deferred
    assert "hexTalent = 237" not in deferred


def test_native_selene_entry_point_is_preserved():
    # SpellDrop remains the native Selene choice entry point; targeted exact
    # acquisition is additional and must not replace this path.
    assert 'if rewardId == "SpellDrop" then' in LUA
    assert 'RewardOverride = "SpellDrop"' in LUA
    assert '"SpawnRoomReward"' in LUA


def test_resident_revision_advances_for_selene_semantics():
    current = int(re.search(r"version = 1, revision = (\d+)", LUA).group(1))
    previous = int(re.search(r"previousModule\.revision ~= (\d+)", LUA).group(1))
    assert current == previous == 63
    assert "resident runtime revision: 63" in STATUS


if __name__ == "__main__":
    test_selene_exact_catalog_is_owner_backed()
    test_selene_mutation_owns_spell_and_tree_lifecycle()
    test_selene_current_run_capabilities_are_typed()
    test_native_selene_entry_point_is_preserved()
    test_resident_revision_advances_for_selene_semantics()
    print("hades2_selene_owner_lifecycle_ok")
