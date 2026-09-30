from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LUA = (ROOT / "Backend/games/hades2/runtime/hades.lua").read_text()
SCHEMA = (ROOT / "Backend/games/hades2/schema.py").read_text()
CATALOG = (ROOT / "Backend/games/hades2/catalog.py").read_text()
API = (ROOT / "Sources/Hades2/Hades2API.swift").read_text()
TYPES = (ROOT / "Sources/Hades2/Hades2Types.swift").read_text()
STATE = (ROOT / "Sources/Hades2/Hades2BackendState.swift").read_text()
MODEL = (ROOT / "Sources/Hades2/Hades2Model.swift").read_text()
VIEW = (ROOT / "Sources/Hades2/Hades2View.swift").read_text()


def test_live_trait_inventory_carries_target_snapshot_and_operation_capabilities():
    for token in (
        "generationId",
        "runId",
        "instanceId",
        "level",
        "rarity",
        "availableRarities",
        "levelCapability",
        "rarityCapability",
        "removalCapability",
        "levelReason",
        "rarityReason",
        "removalReason",
        "deferredIssue",
    ):
        assert token in LUA

    assert "TRAIT_LEVEL_INCREASE_ONE" in SCHEMA
    assert "TRAIT_RARITY_SET_EXACT" in SCHEMA
    assert "TRAIT_REMOVAL_SINGLE_INSTANCE_FORCE" in SCHEMA
    assert "TRAIT_REMOVAL_NAME_LEVEL" in SCHEMA


def test_current_run_traits_reuse_official_bilingual_localization_seam():
    assert "currentRunTraits" in CATALOG
    assert "displayName" in CATALOG
    assert "englishName" in CATALOG
    assert "_SPECIAL_SOURCE_LOCALIZATION_IDS" in CATALOG
    assert "sourceName" in CATALOG
    assert "sourceEnglishName" in CATALOG

    assert "displayName" in TYPES
    assert "englishName" in TYPES
    assert "sourceName" in TYPES
    assert "sourceEnglishName" in TYPES


def test_level_rarity_and_removal_are_non_idempotent_targeted_commands():
    assert 'case setTraitLevel = "set_trait_level"' in API
    assert 'case setTraitRarity = "set_trait_rarity"' in API
    assert 'case removeTrait = "remove_trait"' in API

    assert 'remove_trait = { "trait" }' not in LUA
    for command in ("set_trait_level", "set_trait_rarity", "remove_trait"):
        assert f'{command} = {{ "generationId", "runId", "instanceId", "trait", "family"' in LUA

    assert 'if command == "set_trait_level" then' in LUA
    assert 'if command == "set_trait_rarity" then' in LUA
    assert 'if command == "remove_trait" then' in LUA
    assert "return action(command, params" in LUA
    assert "MGT_OUTCOME_UNKNOWN" in LUA


def test_request_dedup_precedes_live_trait_preflight():
    action_block = LUA[LUA.index("local function action(command, params, work, preflight)"):LUA.index("local function editResource")]
    assert action_block.index("if prior then") < action_block.index("if preflight ~= nil then preflight() end")
    assert "return result\n    end\n    -- Deterministic validation belongs after request-id deduplication." in action_block

    for command, validator in (
        ("set_trait_level", "validateLevelTarget"),
        ("set_trait_rarity", "validateRarityTarget"),
        ("remove_trait", "validateRemovalTarget"),
    ):
        start = LUA.index(f'if command == "{command}" then')
        end = LUA.find('\n    if command == "', start + 1)
        block = LUA[start:] if end < 0 else LUA[start:end]
        assert f"end, {validator})" in block
        assert block.count(f"{validator}()") >= 1


def test_mutations_re_resolve_the_exact_live_selection_before_apply():
    assert "resolveTraitTarget" in LUA
    assert "Trait selection belongs to a stale runtime generation" in LUA
    assert "Trait selection belongs to a stale run" in LUA
    assert "Trait instance is no longer present" in LUA
    assert "Trait target changed since selection" in LUA
    assert "expectedLevel" in LUA
    assert "expectedRarity" in LUA
    assert "sameNameCount" in LUA

    # Level uses the game's owner path, but refuses ambiguous same-name targets
    # because IncreaseTraitLevel uses AreTraitsIdentical rather than a raw id.
    assert "IncreaseTraitLevel(live, 1)" in LUA
    assert "multipleMatchingInstances" in LUA

    # Rarity uses the game's own recompute path; assigning Rarity alone is not
    # accepted because it would leave mounted effect values stale.
    assert "AddRarityToTraits" in LUA
    assert "ForceUpgrade = { live }" in LUA
    assert "target.Rarity = params.rarity" not in LUA


def test_owner_family_controls_default_native_paths():
    family_block = LUA[LUA.index("local function traitFamily"):LUA.index("local function availableRarities")]
    capability_block = LUA[LUA.index("local function operationCapabilities"):LUA.index("local currentRunTraits = function()")]

    assert 'string.find(source, "NPC_", 1, true) == 1' in family_block
    assert 'return "directSpecial"' in family_block
    assert 'family == "olympianHermes" and nativeLevelEligible(trait)' in capability_block
    assert 'family == "olympianHermes" and sellEligible' in capability_block
    assert 'GetAllUpgradeableGodTraits, 1' in LUA

    # Only the audited direct examples may bypass ordinary menu eligibility in
    # this task. Other owner-specific families remain delegated to #236-#240.
    assert 'CritBonusBoon = { sourceId = "Artemis", level = "increaseOne" }' in LUA
    assert 'OmegaExplodeBoon = { sourceId = "Icarus", rarity = "setExact", removal = "singleInstanceForce" }' in LUA
    for family, issue in (
        ("chaos", "236"), ("hex", "237"), ("hammer", "238"),
        ("costume", "239"), ("temporary", "239"), ("directSpecial", "239"),
        ("familiar", "240"), ("other", "221"),
    ):
        assert f"{family} = {issue}" in LUA


def test_force_removal_is_bounded_and_native_sell_scope_stays_explicit():
    assert 'CritBonusBoon' in LUA
    assert 'directSpecial' in LUA
    assert 'singleInstanceForce' in LUA
    assert 'nameLevelAllMatching' in LUA
    assert "RemoveTraitData(CurrentRun.Hero, live" in LUA
    assert "RemoveWeaponTrait(live.Name" in LUA
    assert "SkipExpire = true" in LUA

    # Owner-specific families remain visible and deferred instead of falling
    # through to an arbitrary RemoveTraitData escape hatch.
    for issue in ("236", "237", "238", "239", "240"):
        assert issue in LUA


def test_swift_contract_carries_snapshot_not_just_trait_name():
    for token in (
        "generationID",
        "runID",
        "instanceID",
        "level",
        "rarity",
        "availableRarities",
        "levelCapability",
        "rarityCapability",
        "removalCapability",
    ):
        assert token in TYPES
        assert token in STATE

    assert "setTraitLevel(CurrentRunTrait)" in API
    assert "setTraitRarity(CurrentRunTrait, rarity: String)" in API
    assert "removeTrait(CurrentRunTrait)" in API
    for token in ("generationId", "runId", "instanceId", "expectedLevel", "expectedRarity", "expectedSameNameCount"):
        assert token in API


def test_live_manager_is_searchable_grouped_and_shows_real_controls():
    assert "traitSearch" in VIEW
    assert "filteredCurrentRunTraits" in VIEW
    assert "currentRunTraitFamilies" in VIEW
    assert "traitFamilyLabel" in VIEW
    assert "displayName" in VIEW
    assert "englishName" in VIEW
    assert "hades2.traits.level" in VIEW
    assert "trait.rarity" in VIEW
    assert "availableRarities" in VIEW
    assert "model.increaseTraitLevel(trait)" in VIEW
    assert "model.setTraitRarity(trait" in VIEW
    assert "model.removeTrait(trait)" in VIEW
    assert "Text(trait.name)" in VIEW
    assert "traitLimitationRows" in VIEW
    assert "trait.levelReason" in VIEW
    assert "trait.rarityReason" in VIEW
    assert "trait.removalReason" in VIEW

    assert "func increaseTraitLevel(_ trait: CurrentRunTrait)" in MODEL
    assert "func setTraitRarity(_ trait: CurrentRunTrait, rarity: String)" in MODEL
    assert "func removeTrait(_ trait: CurrentRunTrait)" in MODEL


def test_resident_revision_advances_for_the_new_runtime_contract():
    assert "revision = 55" in LUA


if __name__ == "__main__":
    test_live_trait_inventory_carries_target_snapshot_and_operation_capabilities()
    test_current_run_traits_reuse_official_bilingual_localization_seam()
    test_level_rarity_and_removal_are_non_idempotent_targeted_commands()
    test_request_dedup_precedes_live_trait_preflight()
    test_mutations_re_resolve_the_exact_live_selection_before_apply()
    test_owner_family_controls_default_native_paths()
    test_force_removal_is_bounded_and_native_sell_scope_stays_explicit()
    test_swift_contract_carries_snapshot_not_just_trait_name()
    test_live_manager_is_searchable_grouped_and_shows_real_controls()
    test_resident_revision_advances_for_the_new_runtime_contract()
    print("hades2_live_trait_management_ok")
