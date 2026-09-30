import shutil
import subprocess
import tempfile
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "Backend/games/hades2/runtime/hades.lua"
LUA = shutil.which("lua5.2") or shutil.which("lua")

if not LUA:
    raise SystemExit("a Lua runtime is required for exact-boon runtime behavior tests")

HARNESS = r'''
local runtimePath = assert(arg[1], "runtime path required")

SessionState = {}
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

CodexOrdering = {
  OlympianGods = { "ZeusUpgrade", "HermesUpgrade" },
  Order = {},
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

LootData = {
  ZeusUpgrade = {
    Name = "ZeusUpgrade",
    PriorityUpgrades = { "ZeusWeaponBoon" },
    WeaponUpgrades = { "ZeusWeaponBoon" },
    Traits = { "ZeusCastBoon", "ZeusBlockedBoon" },
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
    Rarity = args.Rarity or "Common",
    StackNum = args.StackNum or 1,
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
    data = { Name = args.TraitName, Rarity = "Common", StackNum = 1 }
  end
  nextId = nextId + 1
  data.Id = nextId
  data.FromLootObserved = args.FromLoot == true
  data.PreProcessedObserved = args.PreProcessedForDisplay == true
  CurrentRun.Hero.Traits[#CurrentRun.Hero.Traits + 1] = data
  return data
end

SetupCostume = function() calls.costume = calls.costume + 1 end

dofile(runtimePath)
local M = assert(__MacGamingTrainerV1, "resident runtime did not initialize")
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

-- Catalog projection: individual NPC traits leave the character-reward group,
-- while ordinary source-owned targets join the same exact-acquisition list.
do
  local ordinary = findReward("exact:ZeusUpgrade:ZeusWeaponBoon")
  eq(ordinary.group, "exact", "ordinary exact group")
  eq(ordinary.trait, "ZeusWeaponBoon", "ordinary exact trait identity")
  eq(ordinary.sourceId, "ZeusUpgrade", "ordinary exact source")
  eq(ordinary.acquisitionMode, "ordinaryNative", "ordinary acquisition mode")

  local direct = findReward("trait:CritBonusBoon")
  eq(direct.group, "exact", "direct NPC exact group")
  eq(direct.acquisitionMode, "direct", "direct NPC mode")

  local costume = findReward("trait:AgilityCostume")
  eq(costume.group, "exact", "costume exact group")
  eq(costume.acquisitionMode, "costume", "costume mode")
end

-- Ordinary add: source eligibility is resolved at operation time and the
-- selected processed trait is applied with native FromLoot semantics.
do
  resetTraits()
  eligibleTarget = "ZeusCastBoon"
  replacementTarget = nil
  local beforeAdd = calls.add
  local result = M.dispatch("spawn_reward", {
    reward = "exact:ZeusUpgrade:ZeusCastBoon",
    requestId = "ordinary-add",
    includeCatalogs = false,
  })
  eq(calls.add, beforeAdd + 1, "ordinary add count")
  local added = CurrentRun.Hero.Traits[1]
  eq(added.Name, "ZeusCastBoon", "ordinary target")
  check(added.FromLootObserved, "ordinary add did not preserve FromLoot")
  check(added.PreProcessedObserved, "ordinary add did not use processed native data")
  eq(added.Rarity, "Rare", "ordinary native rarity")
  eq(result.actionOutcome, "completed", "ordinary action outcome")

  local duplicate = M.dispatch("spawn_reward", {
    reward = "exact:ZeusUpgrade:ZeusCastBoon",
    requestId = "ordinary-add",
    includeCatalogs = false,
  })
  eq(calls.add, beforeAdd + 1, "completed request replayed ordinary add")
  check(duplicate.duplicate == true, "ordinary duplicate request not identified")

  expectError("already owned", function()
    M.dispatch("spawn_reward", {
      reward = "exact:ZeusUpgrade:ZeusCastBoon",
      requestId = "ordinary-owned",
      includeCatalogs = false,
    })
  end)
  eq(calls.add, beforeAdd + 1, "already-owned target mutated")
end

-- Slot replacement follows the native replacement descriptor and removes the
-- occupied trait before adding the processed replacement.
do
  resetTraits({ Name = "OldSlotBoon", Id = 900, Rarity = "Rare", StackNum = 1 })
  eligibleTarget = nil
  replacementTarget = "ZeusWeaponBoon"
  local beforeAdd, beforeRemove = calls.add, calls.remove
  M.dispatch("spawn_reward", {
    reward = "exact:ZeusUpgrade:ZeusWeaponBoon",
    requestId = "ordinary-replace",
    includeCatalogs = false,
  })
  eq(calls.remove, beforeRemove + 1, "replacement did not remove occupied trait")
  eq(calls.add, beforeAdd + 1, "replacement did not add target")
  eq(#CurrentRun.Hero.Traits, 1, "replacement left unexpected trait count")
  eq(CurrentRun.Hero.Traits[1].Name, "ZeusWeaponBoon", "replacement target")
  eq(CurrentRun.Hero.Traits[1].Rarity, "Epic", "replacement rarity")
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
    requestId = "direct-add",
    includeCatalogs = false,
  })
  eq(calls.add, beforeAdd + 1, "direct add count")
  check(CurrentRun.Hero.Traits[1].FromLootObserved, "direct add lost FromLoot")
  expectError("already owned", function()
    M.dispatch("spawn_reward", {
      reward = "trait:CritBonusBoon",
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

with tempfile.TemporaryDirectory(prefix="mgt-exact-boon-runtime-") as td:
    td = Path(td)
    harness = td / "exact_boon_runtime.lua"
    runtime_copy = td / "hades.runtime-under-test.lua"
    harness.write_text(textwrap.dedent(HARNESS), encoding="utf-8")

    source = RUNTIME.read_text(encoding="utf-8")

    def lower_chunk_local(line: str) -> str:
        if not line.startswith("  local "):
            return line
        body = line[len("  local "):]
        if body.startswith("function ") or "=" in body:
            return "  " + body
        names = [name.strip() for name in body.split(",")]
        return "  " + ", ".join(names) + " = " + ", ".join("nil" for _ in names)

    runtime_copy.write_text(
        "\n".join(lower_chunk_local(line) for line in source.splitlines()) + "\n",
        encoding="utf-8",
    )

    proc = subprocess.run(
        [LUA, str(harness), str(runtime_copy)],
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
