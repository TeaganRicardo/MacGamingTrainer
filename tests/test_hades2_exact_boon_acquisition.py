import subprocess
import tempfile
import textwrap
from pathlib import Path

from lua_runtime_support import RESIDENT_DISPATCH_CONTRACT, require_lua52, terminal_case_sources

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "Backend/games/hades2/runtime/hades.lua"
LUA = require_lua52("exact-boon runtime behavior tests")

HARNESS = r'''
local runtimePath = assert(arg[1], "runtime path required")
local contractPath = assert(arg[2], "dispatch contract path required")

SessionState = {}
GameState = { Resources = {}, LifetimeResourcesGained = {}, RunHistory = {} }
ResourceData = {}
ResourceDisplayOrderData = {}
TraitElementData = {}
EnemyData = {}
PresetEventArgs = {
  ArachneCostumeChoices = {
    UpgradeOptions = {
      { ItemName = "AgilityCostume", Type = "Trait" },
    },
  },
}
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

CodexOrdering = {
  OlympianGods = { "ZeusUpgrade", "HermesUpgrade" },
  Order = {},
}

TraitRarityData = {
  RarityValues = { Common = 1, Rare = 2, Epic = 3, Heroic = 4, Legendary = 5, Duo = 5, Perfect = 6 },
}

TraitData = {}
local function trait(name)
  TraitData[name] = {
    Name = name,
    RarityLevels = { Common = {}, Rare = {}, Epic = {}, Heroic = {} },
  }
end

for _, name in ipairs({
  "ZeusWeaponBoon",
  "ZeusCastBoon",
  "ZeusBlockedBoon",
  "HermesWeaponBoon",
  "CritBonusBoon",
  "AgilityCostume",
  "OldSlotBoon",
}) do
  trait(name)
end
-- Native LegendaryTrait/SynergyTrait shapes: one fixed rarity, no stacking.
TraitData.ZeusLegendaryBoon = {
  Name = "ZeusLegendaryBoon", BlockStacking = true, RarityLevels = { Legendary = {} },
}
TraitData.ZeusHermesDuoBoon = {
  Name = "ZeusHermesDuoBoon", BlockStacking = true, RarityLevels = { Duo = {} },
}

LootData = {
  ZeusUpgrade = {
    Name = "ZeusUpgrade",
    PriorityUpgrades = { "ZeusWeaponBoon" },
    WeaponUpgrades = { "ZeusWeaponBoon" },
    Traits = { "ZeusCastBoon", "ZeusBlockedBoon", "ZeusLegendaryBoon", "ZeusHermesDuoBoon" },
  },
  HermesUpgrade = {
    Name = "HermesUpgrade",
    PriorityUpgrades = {},
    WeaponUpgrades = {},
    Traits = { "HermesWeaponBoon" },
  },
}

UnitSetData = {
  SpecialNPCs = {
    NPC_Artemis_01 = { SpeakerName = "Artemis", Traits = { "CritBonusBoon" } },
    NPC_Arachne_01 = { SpeakerName = "Arachne", Traits = { "AgilityCostume" } },
  },
}

local calls = {
  setTraits = 0,
  processed = 0,
  add = 0,
  remove = 0,
  costume = 0,
}
local eligibleTarget = nil
local replacementTarget = nil
local failAddAfterMutation = false
local nextId = 100

local function hasTrait(name)
  for _, value in ipairs(CurrentRun.Hero.Traits) do
    if type(value) == "table" and value.Name == name then return true end
  end
  return false
end

HeroHasTrait = hasTrait
IsGodTrait = function(name, args)
  return string.find(name or "", "Zeus", 1, true) == 1
    or string.find(name or "", "Hermes", 1, true) == 1
end
GetAllUpgradeableGodTraits = function() return {} end

DeepCopyTable = function(value)
  if type(value) ~= "table" then return value end
  local result = {}
  for key, item in pairs(value) do result[key] = DeepCopyTable(item) end
  return result
end
ShallowCopyTable = function(value)
  local result = {}
  for key, item in pairs(value or {}) do result[key] = item end
  return result
end

GetReplacementTraits = function(priority)
  if replacementTarget == nil then return {} end
  for _, name in ipairs(priority or {}) do
    if name == replacementTarget then
      return {
        {
          ItemName = name,
          Type = "Trait",
          TraitToReplace = "OldSlotBoon",
          OldRarity = "Rare",
          Rarity = "Epic",
        },
      }
    end
  end
  return {}
end

GetEligibleUpgrades = function(_, loot)
  local result = {}
  for _, pool in ipairs({ loot.PriorityUpgrades, loot.WeaponUpgrades, loot.Traits }) do
    for _, name in ipairs(pool or {}) do
      if name == eligibleTarget then
        result[#result + 1] = { ItemName = name, Type = "Trait" }
      end
    end
  end
  return result
end

-- The native offer roll. Exact acquisition must never reach it: this is where
-- the Boon Rarity panel acts on naturally offered boons.
SetTraitsOnLoot = function(loot)
  calls.setTraits = calls.setTraits + 1
  loot.UpgradeOptions = {}
  local wanted = loot.Traits and loot.Traits[1] or nil
  if wanted == eligibleTarget then
    loot.UpgradeOptions = {
      { ItemName = wanted, Type = "Trait", Rarity = "Rare" },
    }
  end
  return loot.UpgradeOptions
end

GetProcessedTraitData = function(args)
  calls.processed = calls.processed + 1
  return {
    Name = args.TraitName,
    Rarity = args.Rarity,
    StackNum = args.StackNum,
    RarityMultiplier = args.RarityMultiplier or 1,
  }
end
GetTraitCount = function(hero, args)
  local count = 0
  for _, value in ipairs(hero.Traits or {}) do
    if value.Name == args.Name then count = count + 1 end
  end
  return count
end
GetTotalHeroTraitValue = function() return 0 end

RemoveWeaponTrait = function(name)
  calls.remove = calls.remove + 1
  local kept = {}
  for _, value in ipairs(CurrentRun.Hero.Traits) do
    if value.Name ~= name then kept[#kept + 1] = value end
  end
  CurrentRun.Hero.Traits = kept
end

AddTraitToHero = function(args)
  calls.add = calls.add + 1
  local data
  if type(args.TraitData) == "table" then
    data = DeepCopyTable(args.TraitData)
  else
    data = GetProcessedTraitData({ TraitName = args.TraitName, Rarity = args.Rarity, StackNum = args.StackNum })
  end
  nextId = nextId + 1
  data.Id = nextId
  data.FromLootObserved = args.FromLoot == true
  data.PreProcessedObserved = args.PreProcessedForDisplay == true
  CurrentRun.Hero.Traits[#CurrentRun.Hero.Traits + 1] = data
  if failAddAfterMutation then
    failAddAfterMutation = false
    error("synthetic exact post-mutation acknowledgement failure")
  end
  return data
end

SetupCostume = function() calls.costume = calls.costume + 1 end

dofile(runtimePath)
local M = assert(__MacGamingTrainerV1, "resident runtime did not initialize")
-- Route every dispatch through the production JSON boundary.
dofile(contractPath)
M.session = SessionState
M.run = CurrentRun
M.hero = CurrentRun.Hero

local function fail(message) error("ASSERTION FAILED: " .. message, 0) end
local function check(value, message) if not value then fail(message) end end
local function eq(actual, expected, message)
  if actual ~= expected then
    fail(message .. ": expected=" .. tostring(expected) .. " actual=" .. tostring(actual))
  end
end
local function contains(value, needle)
  return string.find(tostring(value), needle, 1, true) ~= nil
end
local function expectError(needle, fn)
  local ok, message = pcall(fn)
  if ok then fail("expected error containing " .. needle) end
  if not contains(message, needle) then
    fail("wrong error: expected '" .. needle .. "' got '" .. tostring(message) .. "'")
  end
end
local function resetTraits(...)
  CurrentRun.Hero.Traits = { ... }
end
local function findReward(id)
  local state = M.dispatch("status", { includeCatalogs = true })
  for _, row in ipairs(state.rewards or {}) do
    if row.id == id then return row end
  end
  fail("missing reward " .. tostring(id))
end

local function list(values) return table.concat(values or {}, ",") end

-- Catalog projection: individual NPC traits leave the character-reward group,
-- while ordinary source-owned targets join the same exact-acquisition list.
-- Every exact target states the rarities and level its acquisition accepts,
-- from its own native RarityLevels in TraitRarityData order.
do
  local ordinary = findReward("exact:ZeusUpgrade:ZeusWeaponBoon")
  eq(ordinary.group, "exact", "ordinary exact group")
  eq(ordinary.trait, "ZeusWeaponBoon", "ordinary exact trait identity")
  eq(ordinary.sourceId, "ZeusUpgrade", "ordinary exact source")
  eq(ordinary.acquisitionMode, "ordinaryNative", "ordinary acquisition mode")
  eq(list(ordinary.rarities), "Common,Rare,Epic,Heroic", "ordinary rarities")
  eq(ordinary.supportsLevel, true, "ordinary boon stacks natively")

  local legendary = findReward("exact:ZeusUpgrade:ZeusLegendaryBoon")
  eq(list(legendary.rarities), "Legendary", "Legendary rarity is fixed")
  eq(legendary.supportsLevel, false, "Legendary blocks stacking")
  local duo = findReward("exact:ZeusUpgrade:ZeusHermesDuoBoon")
  eq(list(duo.rarities), "Duo", "Duo rarity is fixed")
  eq(duo.supportsLevel, false, "Duo blocks stacking")

  local direct = findReward("trait:CritBonusBoon")
  eq(direct.group, "exact", "direct NPC exact group")
  eq(direct.acquisitionMode, "direct", "direct NPC mode")
  eq(list(direct.rarities), "Common,Rare,Epic,Heroic", "direct NPC rarities")
  eq(direct.supportsLevel, true, "direct NPC boon stacks natively")

  local costume = findReward("trait:AgilityCostume")
  eq(costume.group, "exact", "costume exact group")
  eq(costume.acquisitionMode, "costume", "costume mode")
  eq(#costume.rarities, 0, "Arachne owns the outfit rarity")
  eq(costume.supportsLevel, false, "Arachne outfit does not stack")
end

-- Ordinary add: source eligibility is resolved at operation time and the
-- selected trait is processed at the caller's rarity and level with native
-- FromLoot semantics. The Boon Rarity panel, here enabled with a different
-- minimum and forced Legendary/Duo, governs only the native offer roll.
do
  M.dispatch("set_boon_rarity", { target = "Heroic", forceLegendary = true, forceDuo = true, includeCatalogs = false })
  M.dispatch("set_feature", { feature = "boonRarityEnabled", value = true, includeCatalogs = false })
  check(M.boonRarityEnabled, "Boon Rarity panel did not engage")

  resetTraits()
  eligibleTarget = "ZeusCastBoon"
  replacementTarget = nil
  -- Exact Trait acquisition belongs to Run/Hero, not to a room-backed reward
  -- context. A distinct hub room must not invalidate the live Trait owner.
  CurrentHubRoom = {}
  local beforeAdd, beforeRoll = calls.add, calls.setTraits
  local result = M.dispatch("spawn_reward", {
    reward = "exact:ZeusUpgrade:ZeusCastBoon",
    rarity = "Epic",
    level = 3,
    requestId = "ordinary-add",
    includeCatalogs = false,
  })
  CurrentHubRoom = nil
  eq(calls.add, beforeAdd + 1, "ordinary add count")
  eq(calls.setTraits, beforeRoll, "exact acquisition consulted the native offer roll")
  local added = CurrentRun.Hero.Traits[1]
  eq(added.Name, "ZeusCastBoon", "ordinary target")
  check(added.FromLootObserved, "ordinary add did not preserve FromLoot")
  check(added.PreProcessedObserved, "ordinary add did not use processed native data")
  eq(added.Rarity, "Epic", "ordinary requested rarity")
  eq(added.StackNum, 3, "ordinary requested level")
  eq(result.actionOutcome, "completed", "ordinary action outcome")

  -- The same Boon Rarity configuration still raises a natural offer.
  local natural = { Name = "ZeusUpgrade", GodLoot = true, Traits = { "ZeusCastBoon" } }
  SetTraitsOnLoot(natural)
  eq(natural.UpgradeOptions[1].Rarity, "Heroic", "natural offer lost the Boon Rarity minimum")

  local duplicate = M.dispatch("spawn_reward", {
    reward = "exact:ZeusUpgrade:ZeusCastBoon",
    rarity = "Epic",
    level = 3,
    requestId = "ordinary-add",
    includeCatalogs = false,
  })
  eq(calls.add, beforeAdd + 1, "completed request replayed ordinary add")
  check(duplicate.duplicate == true, "ordinary duplicate request not identified")

  -- Rarity and level are part of the action identity.
  expectError("requestId reused for a different action", function()
    M.dispatch("spawn_reward", {
      reward = "exact:ZeusUpgrade:ZeusCastBoon", rarity = "Rare", level = 3,
      requestId = "ordinary-add", includeCatalogs = false,
    })
  end)
  expectError("requestId reused for a different action", function()
    M.dispatch("spawn_reward", {
      reward = "exact:ZeusUpgrade:ZeusCastBoon", rarity = "Epic", level = 4,
      requestId = "ordinary-add", includeCatalogs = false,
    })
  end)
  eq(calls.add, beforeAdd + 1, "reused request id mutated")

  expectError("already owned", function()
    M.dispatch("spawn_reward", {
      reward = "exact:ZeusUpgrade:ZeusCastBoon",
      rarity = "Epic",
      requestId = "ordinary-owned",
      includeCatalogs = false,
    })
  end)
  eq(calls.add, beforeAdd + 1, "already-owned target mutated")
end

-- A request outside the target's options is refused before any mutation:
-- a rarity the target lacks, no rarity for a target that has them, a rarity
-- for a target that takes none, and more than one stack of a target that
-- does not stack.
do
  resetTraits()
  eligibleTarget = "ZeusCastBoon"
  replacementTarget = nil
  local beforeAdd = calls.add
  local refusals = {
    { "does not support the requested rarity", { reward = "exact:ZeusUpgrade:ZeusCastBoon", rarity = "Legendary" } },
    { "does not support the requested rarity", { reward = "exact:ZeusUpgrade:ZeusCastBoon" } },
    { "does not support the requested rarity", { reward = "trait:AgilityCostume", rarity = "Common" } },
    { "does not support the requested level", { reward = "exact:ZeusUpgrade:ZeusLegendaryBoon", rarity = "Legendary", level = 2 } },
    { "does not support the requested level", { reward = "trait:AgilityCostume", level = 2 } },
  }
  for index, refusal in ipairs(refusals) do
    local params = refusal[2]
    params.requestId = "acquisition-refused-" .. index
    params.includeCatalogs = false
    expectError(refusal[1], function() M.dispatch("spawn_reward", params) end)
  end
  eq(calls.add, beforeAdd, "refused acquisition options mutated")
  eq(#CurrentRun.Hero.Traits, 0, "refused acquisition options mounted a trait")
end

-- A fixed-rarity target accepts its one native rarity at a single stack.
do
  resetTraits()
  eligibleTarget = "ZeusLegendaryBoon"
  replacementTarget = nil
  M.dispatch("spawn_reward", {
    reward = "exact:ZeusUpgrade:ZeusLegendaryBoon",
    rarity = "Legendary",
    level = 1,
    requestId = "fixed-legendary",
    includeCatalogs = false,
  })
  local added = CurrentRun.Hero.Traits[1]
  eq(added.Name, "ZeusLegendaryBoon", "fixed-rarity target")
  eq(added.Rarity, "Legendary", "fixed rarity")
  eq(added.StackNum, 1, "fixed-rarity single stack")
end

-- If the mutation applies and the acknowledgement path faults, the shared
-- one-shot ledger records outcome-unknown. The same request id is never replayed
-- even though live ownership has already changed.
do
  resetTraits()
  eligibleTarget = "HermesWeaponBoon"
  replacementTarget = nil
  failAddAfterMutation = true
  local beforeAdd = calls.add
  expectError("MGT_OUTCOME_UNKNOWN", function()
    M.dispatch("spawn_reward", {
      reward = "exact:HermesUpgrade:HermesWeaponBoon",
      rarity = "Rare",
      requestId = "ordinary-outcome-unknown",
      includeCatalogs = false,
    })
  end)
  eq(calls.add, beforeAdd + 1, "outcome-unknown exact mutation did not execute once")
  check(hasTrait("HermesWeaponBoon"), "outcome-unknown exact mutation did not alter live state")
  expectError("Previous action outcome is unknown; do not retry", function()
    M.dispatch("spawn_reward", {
      reward = "exact:HermesUpgrade:HermesWeaponBoon",
      rarity = "Rare",
      requestId = "ordinary-outcome-unknown",
      includeCatalogs = false,
    })
  end)
  eq(calls.add, beforeAdd + 1, "outcome-unknown exact request auto-replayed")
end

-- Slot replacement follows the native replacement descriptor and removes the
-- occupied trait before adding the replacement at the requested rarity/level.
do
  resetTraits({ Name = "OldSlotBoon", Id = 900, Rarity = "Rare", StackNum = 1 })
  eligibleTarget = nil
  replacementTarget = "ZeusWeaponBoon"
  local beforeAdd, beforeRemove = calls.add, calls.remove
  M.dispatch("spawn_reward", {
    reward = "exact:ZeusUpgrade:ZeusWeaponBoon",
    rarity = "Heroic",
    level = 2,
    requestId = "ordinary-replace",
    includeCatalogs = false,
  })
  eq(calls.remove, beforeRemove + 1, "replacement did not remove occupied trait")
  eq(calls.add, beforeAdd + 1, "replacement did not add target")
  eq(#CurrentRun.Hero.Traits, 1, "replacement left unexpected trait count")
  eq(CurrentRun.Hero.Traits[1].Name, "ZeusWeaponBoon", "replacement target")
  eq(CurrentRun.Hero.Traits[1].Rarity, "Heroic", "replacement requested rarity")
  eq(CurrentRun.Hero.Traits[1].StackNum, 2, "replacement requested level")
  eq(CurrentRun.Hero.Traits[1].OldRarity, "Rare", "replacement lost native exchange descriptor")
end

-- An ordinary target that is neither a native replacement nor currently
-- eligible fails closed without calling the mutation seam.
do
  resetTraits()
  eligibleTarget = nil
  replacementTarget = nil
  local beforeAdd = calls.add
  expectError("not currently eligible", function()
    M.dispatch("spawn_reward", {
      reward = "exact:ZeusUpgrade:ZeusBlockedBoon",
      rarity = "Common",
      requestId = "ordinary-incompatible",
      includeCatalogs = false,
    })
  end)
  eq(calls.add, beforeAdd, "incompatible ordinary target mutated")
end

-- Existing audited direct paths remain exact acquisitions, reject duplicates,
-- and preserve owner-specific initialization.
do
  resetTraits()
  local beforeAdd = calls.add
  M.dispatch("spawn_reward", {
    reward = "trait:CritBonusBoon",
    rarity = "Rare",
    level = 2,
    requestId = "direct-add",
    includeCatalogs = false,
  })
  eq(calls.add, beforeAdd + 1, "direct add count")
  check(CurrentRun.Hero.Traits[1].FromLootObserved, "direct add lost FromLoot")
  eq(CurrentRun.Hero.Traits[1].Rarity, "Rare", "direct requested rarity")
  eq(CurrentRun.Hero.Traits[1].StackNum, 2, "direct requested level")
  expectError("already owned", function()
    M.dispatch("spawn_reward", {
      reward = "trait:CritBonusBoon",
      rarity = "Rare",
      requestId = "direct-owned",
      includeCatalogs = false,
    })
  end)

  resetTraits()
  local beforeCostume = calls.costume
  M.dispatch("spawn_reward", {
    reward = "trait:AgilityCostume",
    requestId = "costume-add",
    includeCatalogs = false,
  })
  eq(calls.costume, beforeCostume + 1, "Arachne initialization did not run")
end

print("hades2_exact_boon_acquisition_runtime_ok")
'''

TERMINAL_CASES = [
    ('-- If the mutation applies and the acknowledgement path faults', '-- Slot replacement follows the native replacement descriptor'),
]

with tempfile.TemporaryDirectory(prefix="mgt-exact-boon-runtime-") as td:
    td = Path(td)
    for source in terminal_case_sources(HARNESS, TERMINAL_CASES, 'hades2_exact_boon_acquisition_runtime_ok'):
        harness = td / "exact_boon_runtime.lua"
        harness.write_text(textwrap.dedent(source), encoding="utf-8")

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
        assert "hades2_exact_boon_acquisition_runtime_ok" in proc.stdout, proc.stdout
        print(proc.stdout.strip())
