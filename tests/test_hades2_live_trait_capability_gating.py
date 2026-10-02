"""Resident behavior test for live trait capability gating and target identity.

#227 replaced the D01 SellTraits-only mutation model with a snapshot-based
inventory whose mutating commands (``set_trait_level``, ``set_trait_rarity``,
``remove_trait``) are gated by a per-target capability projection. The old
guards that used to protect that family were retired with the D01 model, and the
replacement had no behavioural test at the owning interface -- only source-token
assertions. This is the RED fixture that pins the real contract:

* a trait whose ``operationCapabilities`` project ``none`` (an
  ``ownerSpecificLifecycle`` family) must be *refused* with the capability error
  key, not silently accepted and not silently no-op'd;
* the target snapshot is revalidated immediately before mutation, so an empty,
  foreign or synthetic ``missing:`` ``instanceId`` and a mismatched
  ``expectedSameNameCount`` must all be rejected rather than resolved to a
  different live instance;
* a qualified single-instance trait must actually be removed, and a removal that
  the game-owned callback silently drops must fail closed.

The harness mocks the game globals, loads the shipped resident source, and
routes every dispatch through the production JSON boundary so a payload that is
valid Lua but invalid JSON fails here instead of in the game.
"""

import subprocess
import tempfile
import textwrap
from pathlib import Path

from lua_runtime_support import RESIDENT_DISPATCH_CONTRACT, require_lua52

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "Backend/games/hades2/runtime/hades.lua"
LUA = require_lua52("live trait capability gating runtime tests")

HARNESS = r'''
local runtimePath = assert(arg[1], "runtime path required")
local contractPath = assert(arg[2], "dispatch contract path required")

SessionState = {}
SessionMapState = {}
GameState = { Resources = {}, LifetimeResourcesGained = {}, RunHistory = {} }
ResourceData = {}
ResourceDisplayOrderData = {}
TraitElementData = {}
EnemyData = {}
PresetEventArgs = {}
ScreenData = {}
MapState = { RoomRequiredObjects = {} }
LootObjects = {}
ConsumableData = {}
RewardStoreData = {}
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
    TraitDictionary = {},
    BoonData = { GameStateRequirements = {}, ReplaceChance = 0 },
  },
  CurrentRoom = {},
  NumRerolls = 0,
  SpellCharge = 0,
  PickedTraits = {},
  BannedTraits = {},
}

CodexOrdering = { OlympianGods = {}, Order = {} }
TraitData = {}
LootData = {}
UnitSetData = {}

local calls = { level = 0, rarity = 0, nativeRemove = 0, directRemove = 0 }
local skipDirectRemoval = false
local lastDirectRemoveArgs = nil
local rarityValue = { Common = 1, Rare = 2, Epic = 3, Heroic = 4 }

local function removeMatching(predicate)
  local kept = {}
  for _, trait in ipairs(CurrentRun.Hero.Traits) do
    if not predicate(trait) then kept[#kept + 1] = trait end
  end
  CurrentRun.Hero.Traits = kept
end

-- Ordinary (Olympian) traits are the native Pom/shop-eligible family; the
-- "Chaos" name routes into an owner-specific family whose capabilities project
-- "none". Both predicates mirror the real game-owned callbacks.
IsGodTrait = function(name)
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
  return trait
end

AddRarityToTraits = function(_, args)
  calls.rarity = calls.rarity + 1
  local trait = assert(args.ForceUpgrade and args.ForceUpgrade[1], "missing force-upgrade target")
  trait.Rarity = args.TargetRarityName
  trait.EffectValue = rarityValue[args.TargetRarityName] * 1000
  return trait
end

RemoveWeaponTrait = function(name)
  calls.nativeRemove = calls.nativeRemove + 1
  removeMatching(function(trait) return trait.Name == name end)
end

RemoveTraitData = function(hero, target, args)
  calls.directRemove = calls.directRemove + 1
  lastDirectRemoveArgs = args
  if not skipDirectRemoval then
    removeMatching(function(trait) return trait == target end)
  end
end

local function defineRarities(name)
  TraitData[name] = { RarityLevels = { Common = {}, Rare = {}, Epic = {}, Heroic = {} } }
end

for _, name in ipairs({
  "OrdinaryLevel",
  "OrdinaryDup",
  "OrdinaryCountGuard",
  "ChaosGuard",
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
  CurrentRun.Hero.TraitDictionary = {}
  for _, trait in ipairs(CurrentRun.Hero.Traits) do
    if trait.Name then CurrentRun.Hero.TraitDictionary[trait.Name] = true end
  end
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

local function paramsFrom(row, requestId)
  return {
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
end

-- A: capability gating. An owner-specific trait projects "none"; the mutating
-- commands must refuse it with the capability error key instead of succeeding or
-- silently doing nothing.
do
  local trait = newTrait("ChaosGuard", 101, 1, "Rare")
  setTraits(trait)
  local row = findRow("ChaosGuard", 101)
  eq(row.family, "chaos", "owner-specific family")
  eq(row.levelCapability, "none", "owner-specific level capability")
  eq(row.levelReason, "ownerSpecificLifecycle", "owner-specific level reason")
  eq(row.removalCapability, "none", "owner-specific removal capability")
  local beforeLevel = calls.level
  expectError("Trait level editing is unavailable for the selected target", function()
    M.dispatch("set_trait_level", paramsFrom(row, "gating-level"))
  end)
  eq(calls.level, beforeLevel, "gated level change reached the mutator")
  eq(#CurrentRun.Hero.Traits, 1, "gated level change mutated the inventory")
end

do
  local trait = newTrait("ChaosGuard", 102, 1, "Rare")
  setTraits(trait)
  local row = findRow("ChaosGuard", 102)
  eq(row.removalCapability, "none", "owner-specific removal capability")
  local beforeNative, beforeDirect = calls.nativeRemove, calls.directRemove
  expectError("Trait removal is unavailable for the selected target", function()
    M.dispatch("remove_trait", paramsFrom(row, "gating-removal"))
  end)
  eq(calls.nativeRemove, beforeNative, "gated removal reached the native mutator")
  eq(calls.directRemove, beforeDirect, "gated removal reached the direct mutator")
  eq(#CurrentRun.Hero.Traits, 1, "gated removal mutated the inventory")
end

-- An ambiguous duplicate-name trait also projects "none". Loosening the level
-- capability gate would let the native mutator run here, so the refusal must be
-- driven by the capability projection rather than by an incidental side effect.
do
  local first = newTrait("OrdinaryDup", 201, 1, "Rare")
  local second = newTrait("OrdinaryDup", 202, 1, "Rare")
  setTraits(first, second)
  local row = findRow("OrdinaryDup", 201)
  eq(row.levelCapability, "none", "ambiguous level capability")
  eq(row.levelReason, "multipleMatchingInstances", "ambiguous level reason")
  local beforeLevel = calls.level
  expectError("Trait level editing is unavailable for the selected target", function()
    M.dispatch("set_trait_level", paramsFrom(row, "ambiguous-level"))
  end)
  eq(calls.level, beforeLevel, "ambiguous level change reached the mutator")
end

-- B: target identity recheck. A selection that no longer resolves to exactly
-- one live instance must be rejected before any game-owned callback runs.
do
  local trait = newTrait("OrdinaryLevel", 301, 1, "Rare")
  setTraits(trait)
  local row = findRow("OrdinaryLevel", 301)
  local params = paramsFrom(row, "empty-instance")
  params.instanceId = ""
  local beforeLevel = calls.level
  expectError("Trait instance is no longer present", function()
    M.dispatch("set_trait_level", params)
  end)
  eq(calls.level, beforeLevel, "empty instanceId reached the mutator")
end

do
  local trait = newTrait("OrdinaryLevel", 302, 1, "Rare")
  setTraits(trait)
  local row = findRow("OrdinaryLevel", 302)
  local params = paramsFrom(row, "missing-instance")
  params.instanceId = "missing:1"
  local beforeLevel = calls.level
  expectError("Trait instance is no longer present", function()
    M.dispatch("set_trait_level", params)
  end)
  eq(calls.level, beforeLevel, "missing: instanceId reached the mutator")
end

do
  local trait = newTrait("OrdinaryLevel", 303, 1, "Rare")
  setTraits(trait)
  local row = findRow("OrdinaryLevel", 303)
  local params = paramsFrom(row, "foreign-instance")
  params.instanceId = "999999"
  local beforeLevel = calls.level
  expectError("Trait instance is no longer present", function()
    M.dispatch("set_trait_level", params)
  end)
  eq(calls.level, beforeLevel, "foreign instanceId reached the mutator")
end

-- A changed same-name count is a changed target. A second instance appearing
-- between selection and mutation must be rejected, not treated as a best-effort
-- edit of whichever instance still matches the other fields.
do
  local trait = newTrait("OrdinaryCountGuard", 401, 1, "Rare")
  setTraits(trait)
  local row = findRow("OrdinaryCountGuard", 401)
  eq(row.sameNameCount, 1, "selection-time count")
  local params = paramsFrom(row, "count-mismatch")
  table.insert(CurrentRun.Hero.Traits, newTrait("OrdinaryCountGuard", 402, 1, "Rare"))
  local beforeLevel = calls.level
  expectError("Trait target changed since selection", function()
    M.dispatch("set_trait_level", params)
  end)
  eq(calls.level, beforeLevel, "changed-count target reached the mutator")
end

-- C: forced removal. A qualified single-instance trait is actually removed and
-- the receipt reports a real success.
do
  local trait = newTrait("OmegaExplodeBoon", 501, 1, "Rare")
  setTraits(trait)
  local row = findRow("OmegaExplodeBoon", 501)
  eq(row.removalCapability, "singleInstanceForce", "direct removal capability")
  check(row.removalScopeAllMatching == false, "direct removal scope widened")
  local beforeDirect = calls.directRemove
  local result = M.dispatch("remove_trait", paramsFrom(row, "direct-remove"))
  eq(calls.directRemove, beforeDirect + 1, "direct removal callback count")
  eq(#CurrentRun.Hero.Traits, 0, "direct removal left the instance mounted")
  eq(result.actionOutcome, "completed", "direct removal receipt outcome")
  check(result.applied == true, "direct removal receipt not marked applied")
  check(lastDirectRemoveArgs and lastDirectRemoveArgs.SkipExpire == true,
    "direct removal did not suppress the expiration path")
end

-- A game-owned removal that silently leaves the instance mounted must fail
-- closed rather than present a green success.
do
  local trait = newTrait("OmegaExplodeBoon", 601, 1, "Rare")
  setTraits(trait)
  local row = findRow("OmegaExplodeBoon", 601)
  local beforeDirect = calls.directRemove
  skipDirectRemoval = true
  expectError("MGT_OUTCOME_UNKNOWN", function()
    M.dispatch("remove_trait", paramsFrom(row, "direct-removal-verify"))
  end)
  skipDirectRemoval = false
  eq(calls.directRemove, beforeDirect + 1, "cleanup verification callback count")
  eq(#CurrentRun.Hero.Traits, 1, "cleanup-failure fixture unexpectedly removed the trait")
end

print("hades2_live_trait_capability_gating_ok")
'''

with tempfile.TemporaryDirectory(prefix="mgt-live-trait-gating-") as td:
    td = Path(td)
    harness = td / "live_trait_capability_gating.lua"
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
    assert "hades2_live_trait_capability_gating_ok" in proc.stdout, proc.stdout
    print(proc.stdout.strip())
