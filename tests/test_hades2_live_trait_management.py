from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LUA = (ROOT / "Backend/games/hades2/runtime/hades.lua").read_text()
CATALOG = (ROOT / "Backend/games/hades2/catalog.py").read_text()
TYPES = (ROOT / "Sources/Hades2/Hades2Types.swift").read_text()


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


def test_special_npc_ownership_comes_from_native_source_data():
    source_block = LUA[LUA.index("local function specialTraitSourceId"):LUA.index("local function sellScreenEligible")]
    assert "nativeSpecialChoiceDefinitions" in source_block
    assert "EnemyData[definition.npc]" in source_block
    assert "PresetEventArgs[definition.choices]" in source_block
    assert "option.ItemName == name" in source_block
    assert "specialTraitSourceId(trait.Name)" in source_block
    assert "CheckEnemyData = true" in source_block

    family_block = LUA[LUA.index("local function traitFamily"):LUA.index("local function availableRarities")]
    assert 'nativeSpecialChoiceDefinitions[source] ~= nil' in family_block


def test_owner_family_controls_default_native_paths():
    family_block = LUA[LUA.index("local function traitFamily"):LUA.index("local function availableRarities")]
    capability_block = LUA[LUA.index("local function operationCapabilities"):LUA.index("local currentRunTraits = function()")]

    assert 'string.find(source, "NPC_", 1, true) == 1' in family_block
    assert 'return "directSpecial"' in family_block
    assert 'family == "olympianHermes" and nativeLevelEligible(trait)' in capability_block
    assert 'family == "olympianHermes" and sellEligible' in capability_block
    assert 'GetAllUpgradeableGodTraits, 1' in LUA

    # Only the audited direct examples may bypass ordinary menu eligibility.
    # Chaos is now owner-specifically implemented by #236; the remaining
    # families stay delegated to their own follow-up slices.
    assert 'CritBonusBoon = { sourceId = "Artemis", level = "increaseOne" }' in LUA
    assert 'OmegaExplodeBoon = { sourceId = "Icarus", rarity = "setExact", removal = "singleInstanceForce" }' in LUA
    assert 'family == "chaos"' in capability_block
    assert 'chaosLifecycleState' in LUA
    for family, issue in (
        ("hex", "237"), ("hammer", "238"),
        ("costume", "239"), ("temporary", "239"), ("directSpecial", "239"),
        ("familiar", "240"), ("other", "221"),
    ):
        assert f"{family} = {issue}" in LUA


if __name__ == "__main__":
    test_current_run_traits_reuse_official_bilingual_localization_seam()
    test_special_npc_ownership_comes_from_native_source_data()
    test_owner_family_controls_default_native_paths()
    print("hades2_live_trait_management_ok")

# Executable resident-runtime behavior coverage belongs to this feature owner.
import subprocess
import tempfile
import textwrap
from pathlib import Path

from lua_runtime_support import RESIDENT_DISPATCH_CONTRACT, require_lua52

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "Backend/games/hades2/runtime/hades.lua"
LUA = require_lua52("resident-runtime behavior tests")

HARNESS = r'''
local runtimePath = assert(arg[1], "runtime path required")
local contractPath = assert(arg[2], "dispatch contract path required")

SessionState = {}
GameState = {
  Resources = {},
  LifetimeResourcesGained = {},
  RunHistory = {},
}
ResourceData = {}
ResourceDisplayOrderData = {}
TraitElementData = {}
EnemyData = {}
PresetEventArgs = {}
ScreenData = {}
MapState = { RoomRequiredObjects = {} }
LootObjects = {}
UpdateTimers = function() end

CurrentRun = {
  Hero = {
    ObjectId = 1,
    Health = 100,
    MaxHealth = 100,
    Mana = 50,
    MaxMana = 50,
    HealthBuffer = 0,
    Elements = {},
    Traits = {},
  },
  CurrentRoom = {},
  NumRerolls = 0,
  SpellCharge = 0,
}

local calls = {
  level = 0,
  rarity = 0,
  nativeRemove = 0,
  directRemove = 0,
}
local failLevelAfterMutation = false
local skipNativeRemoval = false
local skipDirectRemoval = false
local lastDirectRemoveArgs = nil

local rarityValue = {
  Common = 1,
  Rare = 2,
  Epic = 3,
  Heroic = 4,
}

local function removeMatching(predicate)
  local kept = {}
  for _, trait in ipairs(CurrentRun.Hero.Traits) do
    if not predicate(trait) then kept[#kept + 1] = trait end
  end
  CurrentRun.Hero.Traits = kept
end

IsGodTrait = function(name, args)
  return string.find(name or "", "Ordinary", 1, true) == 1
end

GetAllUpgradeableGodTraits = function()
  local result = {}
  for _, trait in ipairs(CurrentRun.Hero.Traits) do
    if string.find(trait.Name or "", "Ordinary", 1, true) == 1 and not trait.BlockStacking then
      result[trait.Name] = true
    end
  end
  return result
end

IncreaseTraitLevel = function(trait, amount)
  calls.level = calls.level + 1
  trait.StackNum = (trait.StackNum or 1) + amount
  trait.EffectValue = (trait.EffectValue or 0) + 100 * amount
  if failLevelAfterMutation then
    failLevelAfterMutation = false
    error("synthetic post-mutation failure")
  end
  return trait
end

AddRarityToTraits = function(_, args)
  calls.rarity = calls.rarity + 1
  local trait = assert(args.ForceUpgrade and args.ForceUpgrade[1], "missing force-upgrade target")
  trait.Rarity = args.TargetRarityName
  trait.EffectValue = rarityValue[args.TargetRarityName] * 1000
  return trait
end

RemoveWeaponTrait = function(name, args)
  calls.nativeRemove = calls.nativeRemove + 1
  if not skipNativeRemoval then
    removeMatching(function(trait) return trait.Name == name end)
  end
end

RemoveTraitData = function(hero, target, args)
  calls.directRemove = calls.directRemove + 1
  lastDirectRemoveArgs = args
  if not skipDirectRemoval then
    removeMatching(function(trait) return trait == target end)
  end
end

TraitData = {}

local function defineRarities(name)
  TraitData[name] = {
    RarityLevels = {
      Common = {},
      Rare = {},
      Epic = {},
      Heroic = {},
    },
  }
end

for _, name in ipairs({
  "OrdinaryLevel",
  "OrdinaryRarity",
  "OrdinaryRemove",
  "OrdinaryDuplicate",
  "OrdinaryStale",
  "OrdinaryReplay",
  "OrdinaryOutcomeUnknown",
  "CritBonusBoon",
  "OmegaExplodeBoon",
}) do
  defineRarities(name)
end

dofile(runtimePath)
local M = assert(__MacGamingTrainerV1, "resident runtime did not initialize")
-- Route every dispatch through the production JSON boundary.
dofile(contractPath)
M.session = SessionState
M.run = CurrentRun
M.hero = CurrentRun.Hero

local function fail(message)
  error("ASSERTION FAILED: " .. message, 0)
end

local function check(condition, message)
  if not condition then fail(message) end
end

local function eq(actual, expected, message)
  if actual ~= expected then
    fail(message .. ": expected=" .. tostring(expected) .. " actual=" .. tostring(actual))
  end
end

local function contains(text, needle)
  return string.find(tostring(text), needle, 1, true) ~= nil
end

local function expectError(needle, fn)
  local ok, message = pcall(fn)
  if ok then fail("expected error containing: " .. needle) end
  if not contains(message, needle) then
    fail("wrong error; expected '" .. needle .. "', got '" .. tostring(message) .. "'")
  end
end

local function setTraits(...)
  CurrentRun.Hero.Traits = { ... }
end

local function newTrait(name, id, level, rarity, extra)
  local trait = {
    Name = name,
    Id = id,
    StackNum = level or 1,
    Rarity = rarity or "Common",
    EffectValue = 0,
  }
  if extra then
    for key, value in pairs(extra) do trait[key] = value end
  end
  return trait
end

local function status()
  return M.dispatch("status", { includeCatalogs = false })
end

local function findRow(name, instanceId)
  for _, row in ipairs(status().currentRunTraits or {}) do
    if row.name == name and (instanceId == nil or row.instanceId == tostring(instanceId)) then
      return row
    end
  end
  fail("missing observed trait row " .. tostring(name) .. "/" .. tostring(instanceId))
end

local function paramsFrom(row, requestId, targetLevel)
  local params = {
    requestId = requestId,
    generationId = row.generationId,
    runId = row.runId,
    instanceId = row.instanceId,
    trait = row.name,
    family = row.family,
    expectedLevel = row.level,
    expectedRarity = row.rarity,
    expectedSameNameCount = row.sameNameCount,
    includeCatalogs = false,
  }
  if targetLevel ~= nil then params.targetLevel = targetLevel end
  return params
end

-- Native Pom-eligible level change: execute the resident command and verify
-- the game-owned callback changed both observed level and an effect sentinel.
do
  local trait = newTrait("OrdinaryLevel", 101, 1, "Rare")
  setTraits(trait)
  local row = findRow("OrdinaryLevel", 101)
  eq(row.family, "olympianHermes", "ordinary level family")
  eq(row.levelCapability, "increaseOne", "ordinary level capability")
  local beforeCalls = calls.level
  local result = M.dispatch("set_trait_level", paramsFrom(row, "native-level", 4))
  eq(calls.level, beforeCalls + 1, "native level callback count")
  eq(trait.StackNum, 4, "native target-level mutation")
  eq(trait.EffectValue, 300, "native target-level effect recomputation")
  eq(result.currentRunTraits[1].level, 4, "native target-level observed result")
  eq(result.actionOutcome, "completed", "native level receipt")
end

-- Artemis direct example: native Pom eligibility deliberately says false, so
-- this proves the bounded direct strategy rather than a widened native gate.
do
  local trait = newTrait("CritBonusBoon", 201, 1, "Rare")
  setTraits(trait)
  local row = findRow("CritBonusBoon", 201)
  eq(row.family, "directSpecial", "Artemis direct family")
  eq(row.levelCapability, "increaseOne", "Artemis direct level capability")
  check(GetAllUpgradeableGodTraits(1)[trait.Name] ~= true, "Artemis unexpectedly native-Pom eligible")
  M.dispatch("set_trait_level", paramsFrom(row, "direct-level", 3))
  eq(trait.StackNum, 3, "direct target-level mutation")
  eq(trait.EffectValue, 200, "direct target-level effect mutation")
end

-- Native rarity change must run the game recomputation callback rather than
-- assigning only the displayed rarity field.
do
  local trait = newTrait("OrdinaryRarity", 301, 1, "Common")
  setTraits(trait)
  local row = findRow("OrdinaryRarity", 301)
  eq(row.rarityCapability, "setExact", "ordinary rarity capability")
  local params = paramsFrom(row, "native-rarity")
  params.rarity = "Epic"
  local beforeCalls = calls.rarity
  local result = M.dispatch("set_trait_rarity", params)
  eq(calls.rarity, beforeCalls + 1, "native rarity recompute count")
  eq(trait.Rarity, "Epic", "native rarity mutation")
  eq(trait.EffectValue, 3000, "native rarity effect recomputation")
  eq(result.currentRunTraits[1].rarity, "Epic", "native rarity observed result")
end

-- Icarus direct rarity is intentionally not shop/native eligible and still
-- follows AddRarityToTraits so mounted effect values are recomputed.
do
  local trait = newTrait("OmegaExplodeBoon", 401, 1, "Common")
  setTraits(trait)
  local row = findRow("OmegaExplodeBoon", 401)
  eq(row.family, "directSpecial", "Icarus direct family")
  eq(row.rarityCapability, "setExact", "Icarus direct rarity capability")
  check(not IsGodTrait(trait.Name, { ForShop = true }), "Icarus unexpectedly native-shop eligible")
  local params = paramsFrom(row, "direct-rarity")
  params.rarity = "Heroic"
  M.dispatch("set_trait_rarity", params)
  eq(trait.Rarity, "Heroic", "direct rarity mutation")
  eq(trait.EffectValue, 4000, "direct rarity effect recomputation")
end

-- Native SellTraits-equivalent removal is explicitly name-level/all-matching.
do
  local first = newTrait("OrdinaryRemove", 501, 1, "Rare")
  local second = newTrait("OrdinaryRemove", 502, 1, "Rare")
  setTraits(first, second)
  local row = findRow("OrdinaryRemove", 501)
  eq(row.sameNameCount, 2, "native removal duplicate count")
  eq(row.removalCapability, "nameLevelAllMatching", "native removal capability")
  check(row.removalScopeAllMatching == true, "native removal scope not explicit")
  local beforeCalls = calls.nativeRemove
  local result = M.dispatch("remove_trait", paramsFrom(row, "native-remove"))
  eq(calls.nativeRemove, beforeCalls + 1, "native removal callback count")
  eq(#CurrentRun.Hero.Traits, 0, "native removal did not clean every same-name instance")
  eq(#result.currentRunTraits, 0, "native removal observed inventory not empty")
end

-- Direct Icarus removal is single-instance and executes RemoveTraitData cleanup
-- with SkipExpire so no one-shot expiration/reward path is replayed.
do
  local first = newTrait("OmegaExplodeBoon", 601, 1, "Rare")
  local second = newTrait("OmegaExplodeBoon", 602, 1, "Rare")
  setTraits(first, second)
  local row = findRow("OmegaExplodeBoon", 601)
  eq(row.sameNameCount, 2, "direct removal duplicate count")
  eq(row.removalCapability, "singleInstanceForce", "direct removal capability")
  check(row.removalScopeAllMatching == false, "direct removal scope widened")
  local beforeCalls = calls.directRemove
  M.dispatch("remove_trait", paramsFrom(row, "direct-remove"))
  eq(calls.directRemove, beforeCalls + 1, "direct removal callback count")
  eq(#CurrentRun.Hero.Traits, 1, "direct removal removed wrong number of instances")
  eq(CurrentRun.Hero.Traits[1].Id, 602, "direct removal removed wrong instance")
  check(lastDirectRemoveArgs and lastDirectRemoveArgs.SkipExpire == true, "direct removal did not suppress expiration path")
end

-- Identical-name instances are deliberately ambiguous for object-sensitive
-- level/rarity operations; the runtime must fail before calling the mutator.
do
  local first = newTrait("OrdinaryDuplicate", 701, 1, "Rare")
  local second = newTrait("OrdinaryDuplicate", 702, 1, "Rare")
  setTraits(first, second)
  local row = findRow("OrdinaryDuplicate", 701)
  eq(row.levelCapability, "none", "duplicate-name level capability")
  eq(row.rarityCapability, "none", "duplicate-name rarity capability")
  local beforeLevel = calls.level
  expectError("Trait level editing is unavailable", function()
    M.dispatch("set_trait_level", paramsFrom(row, "duplicate-level", row.level + 1))
  end)
  eq(calls.level, beforeLevel, "duplicate-name level reached mutator")
end

-- Stale generation/run/changed target snapshots are rejected during preflight,
-- before any game-owned mutation callback is reached.
do
  local trait = newTrait("OrdinaryStale", 801, 1, "Rare")
  setTraits(trait)
  local row = findRow("OrdinaryStale", 801)
  local beforeLevel = calls.level

  local staleGeneration = paramsFrom(row, "stale-generation", row.level + 1)
  staleGeneration.generationId = "old-generation"
  expectError("stale runtime generation", function()
    M.dispatch("set_trait_level", staleGeneration)
  end)

  local staleRun = paramsFrom(row, "stale-run", row.level + 1)
  staleRun.runId = "old-run"
  expectError("stale run", function()
    M.dispatch("set_trait_level", staleRun)
  end)

  local changed = paramsFrom(row, "changed-target", row.level + 1)
  trait.StackNum = 2
  expectError("Trait target changed since selection", function()
    M.dispatch("set_trait_level", changed)
  end)
  eq(calls.level, beforeLevel, "stale target reached level mutator")
end

-- Completed request IDs deduplicate before stale-target revalidation. The live
-- target has changed after the first mutation, but retry returns the receipt and
-- never applies the non-idempotent operation twice.
do
  local trait = newTrait("OrdinaryReplay", 901, 1, "Rare")
  setTraits(trait)
  local row = findRow("OrdinaryReplay", 901)
  local params = paramsFrom(row, "dedup-level", row.level + 1)
  local beforeLevel = calls.level
  local first = M.dispatch("set_trait_level", params)
  local second = M.dispatch("set_trait_level", params)
  eq(calls.level, beforeLevel + 1, "completed request replayed mutation")
  check(first.duplicate == false, "first request marked duplicate")
  check(second.duplicate == true, "duplicate request not identified")
  eq(second.actionOutcome, "completed", "duplicate receipt lost outcome")
end

-- A post-mutation exception makes the result outcome-unknown. Reissuing the
-- same request ID must fail before mutation even though the first call already
-- changed the live object.
do
  local trait = newTrait("OrdinaryOutcomeUnknown", 1001, 1, "Rare")
  setTraits(trait)
  local row = findRow("OrdinaryOutcomeUnknown", 1001)
  local params = paramsFrom(row, "unknown-level", row.level + 1)
  local beforeLevel = calls.level
  failLevelAfterMutation = true
  expectError("MGT_OUTCOME_UNKNOWN", function()
    M.dispatch("set_trait_level", params)
  end)
  eq(calls.level, beforeLevel + 1, "outcome-unknown mutation did not execute once")
  eq(trait.StackNum, 2, "outcome-unknown sentinel did not model applied mutation")
  expectError("Previous action outcome is unknown; do not retry", function()
    M.dispatch("set_trait_level", params)
  end)
  eq(calls.level, beforeLevel + 1, "outcome-unknown request auto-replayed")
end

-- The runtime verifies removal cleanup instead of trusting the callback return.
do
  local trait = newTrait("OmegaExplodeBoon", 1101, 1, "Rare")
  setTraits(trait)
  local row = findRow("OmegaExplodeBoon", 1101)
  local beforeRemove = calls.directRemove
  skipDirectRemoval = true
  expectError("MGT_OUTCOME_UNKNOWN", function()
    M.dispatch("remove_trait", paramsFrom(row, "direct-cleanup-failure"))
  end)
  skipDirectRemoval = false
  eq(calls.directRemove, beforeRemove + 1, "direct cleanup callback count")
  eq(#CurrentRun.Hero.Traits, 1, "cleanup-failure fixture unexpectedly removed trait")
end

-- Direct strategies with acquisition/expiration lifecycle markers fail closed;
-- changing level must not rerun or bypass those one-shot paths.
do
  local trait = newTrait("CritBonusBoon", 1201, 1, "Rare", {
    AcquireFunctionName = "SyntheticOneShotAcquire",
  })
  setTraits(trait)
  local row = findRow("CritBonusBoon", 1201)
  eq(row.levelCapability, "none", "unsafe direct lifecycle exposed level mutation")
  local beforeLevel = calls.level
  expectError("Trait level editing is unavailable", function()
    M.dispatch("set_trait_level", paramsFrom(row, "unsafe-direct-level", row.level + 1))
  end)
  eq(calls.level, beforeLevel, "unsafe direct lifecycle reached level mutator")
end

print("hades2_live_trait_runtime_behavior_ok")
'''

with tempfile.TemporaryDirectory(prefix="mgt-live-trait-runtime-") as td:
    td = Path(td)
    harness = td / "live_trait_runtime_behavior.lua"
    harness.write_text(textwrap.dedent(HARNESS), encoding="utf-8")

    proc = subprocess.run(
        [LUA, str(harness), str(RUNTIME), str(RESIDENT_DISPATCH_CONTRACT)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=30,
    )
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr)
        raise SystemExit(proc.returncode)
    assert "hades2_live_trait_runtime_behavior_ok" in proc.stdout, proc.stdout
    print(proc.stdout.strip())
