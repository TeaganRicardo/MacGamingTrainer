import subprocess
import tempfile
import textwrap
from pathlib import Path

from lua_runtime_support import RESIDENT_DISPATCH_CONTRACT, require_lua52

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "Backend/games/hades2/runtime/hades.lua"
LUA = require_lua52("store/reward spawn runtime behavior tests")

HARNESS = r'''
local runtimePath = assert(arg[1], "runtime path required")
local contractPath = assert(arg[2], "dispatch contract path required")

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
UpdateTimers = function() end
CodexOrdering = { OlympianGods = {}, Order = {} }
UnitSetData = { SpecialNPCs = {} }

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
  CurrentRoom = {
    Store = {
      StoreOptions = {
        {
          Processed = true,
          ResourceCosts = { Money = 100 },
          DataOverrides = { ResourceCosts = { Money = 100 } },
        },
      },
    },
  },
  NumRerolls = 0,
  SpellCharge = 0,
  PickedTraits = {},
  BannedTraits = {},
}

local function copy(value)
  if type(value) ~= "table" then return value end
  local result = {}
  for key, item in pairs(value) do result[key] = copy(item) end
  return result
end
DeepCopyTable = copy
ShallowCopyTable = function(value)
  local result = {}
  for key, item in pairs(value or {}) do result[key] = item end
  return result
end

TraitData = {
  TemporaryDiscountTrait = {
    Name = "TemporaryDiscountTrait",
    RemainingUses = 2,
    StoreCostMultiplier = 0.8,
    RarityLevels = { Common = {}, Rare = {}, Epic = {}, Heroic = {} },
  },
  ExtendedShopTrait = {
    Name = "ExtendedShopTrait",
    RarityLevels = { Common = {}, Rare = {}, Epic = {}, Heroic = {} },
  },
}

ConsumableData = {
  RandomLoot = {},
  BoostedRandomLoot = {},
  WeaponUpgradeDrop = {},
  ShopHermesUpgrade = {},
  TalentDrop = {},
}

LootData = {
  SpellDrop = { Name = "SpellDrop" },
  SpecialLoot = {
    Name = "SpecialLoot",
    RequiredPackage = "SpecialPkg",
    SetupEvents = {
      { FunctionName = "PregenerateSpells", Args = {} },
    },
  },
  UnsafeLoot = {
    Name = "UnsafeLoot",
    SetupEvents = {
      { FunctionName = "DangerousSetup", Args = {} },
    },
  },
}
RewardStoreData = {
  TestRewards = {
    { Name = "SpecialLoot" },
    { Name = "UnsafeLoot" },
  },
}
GameData = {
  MissingPackages = {
    SpecialLoot = { "ExtraPkg" },
  },
}

local calls = {
  processed = 0,
  add = 0,
  recalc = 0,
  updateTrait = 0,
  useBossExtension = 0,
  obstacle = 0,
  consumable = 0,
  weaponLoot = 0,
  hermesLoot = 0,
  giveLoot = 0,
  roomReward = 0,
  loadPackages = 0,
  createLoot = 0,
}
local nextTraitId = 100
local lastConsumableArgs = nil
local lastWeaponArgs = nil
local lastHermesArgs = nil
local lastHermesLoot = nil
local lastGiveArgs = nil
local lastGiveLoot = nil
local lastRoomRewardArgs = nil
local lastLoadedPackages = nil
local lastCreateLootArgs = nil

local function heroTrait(name)
  for _, value in ipairs(CurrentRun.Hero.Traits or {}) do
    if type(value) == "table" and value.Name == name then return value end
  end
  return nil
end

HeroHasTrait = function(name) return heroTrait(name) ~= nil end
GetHeroTrait = heroTrait
IsTraitActive = function() return true end
IsGodTrait = function() return false end
GetAllUpgradeableGodTraits = function() return {} end
GetEligibleUpgrades = function() return {} end

GetProcessedTraitData = function(args)
  calls.processed = calls.processed + 1
  local data = copy(TraitData[args.TraitName] or {})
  data.Name = args.TraitName
  data.Rarity = args.Rarity or data.Rarity or "Common"
  data.StackNum = args.StackNum or data.StackNum or 1
  return data
end

RecalculateStoreTraitDurations = function()
  calls.recalc = calls.recalc + 1
end

AddTraitToHero = function(args)
  calls.add = calls.add + 1
  local data = type(args.TraitData) == "table" and copy(args.TraitData)
    or { Name = args.TraitName, Rarity = "Common", StackNum = 1 }
  nextTraitId = nextTraitId + 1
  data.Id = nextTraitId
  CurrentRun.Hero.Traits[#CurrentRun.Hero.Traits + 1] = data
  return data
end

UpdateTraitNumber = function()
  calls.updateTrait = calls.updateTrait + 1
end

UseHeroTraitsWithValue = function(name, value)
  if name == "BossExtension" and value == true then
    calls.useBossExtension = calls.useBossExtension + 1
  end
end

SpawnObstacle = function(args)
  calls.obstacle = calls.obstacle + 1
  return 500 + calls.obstacle
end

CreateConsumableItem = function(objectId, name, cost, args)
  calls.consumable = calls.consumable + 1
  lastConsumableArgs = { objectId = objectId, name = name, cost = cost, args = args }
  return { ObjectId = objectId }
end

CreateWeaponLoot = function(args)
  calls.weaponLoot = calls.weaponLoot + 1
  lastWeaponArgs = args
  return { ObjectId = 601 }
end

CreateHermesLoot = function(args)
  calls.hermesLoot = calls.hermesLoot + 1
  lastHermesArgs = args
  lastHermesLoot = { ObjectId = 602, CanReceiveGift = true }
  return lastHermesLoot
end

GetEligibleInteractedGod = function() return "ZeusUpgrade" end
GiveLoot = function(args)
  calls.giveLoot = calls.giveLoot + 1
  lastGiveArgs = args
  local objectId = args.BoonRaritiesOverride ~= nil and 604 or 603
  lastGiveLoot = { ObjectId = objectId, CanReceiveGift = true }
  return lastGiveLoot
end

SpawnRoomReward = function(room, args)
  calls.roomReward = calls.roomReward + 1
  lastRoomRewardArgs = args
  return { ObjectId = 605 }
end

LoadPackages = function(args)
  calls.loadPackages = calls.loadPackages + 1
  lastLoadedPackages = args
end

PregenerateSpells = function() end
CreateLoot = function(args)
  calls.createLoot = calls.createLoot + 1
  lastCreateLootArgs = args
  return { ObjectId = 606 }
end

dofile(runtimePath)
local M = assert(__MacGamingTrainerV1, "resident runtime did not initialize")
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
local function packagePresent(name)
  local names = type(lastLoadedPackages) == "table" and lastLoadedPackages.Names or {}
  for _, value in ipairs(names or {}) do
    if value == name then return true end
  end
  return false
end

-- Store traits use processed native data, recalculate durations, and invalidate
-- already-instantiated shop options when price semantics change.
do
  resetTraits()
  TraitData.TemporaryDiscountTrait.IncreaseUsesOnStack = false
  local option = CurrentRun.CurrentRoom.Store.StoreOptions[1]
  option.Processed = true
  option.ResourceCosts = { Money = 100 }
  option.DataOverrides = { ResourceCosts = { Money = 100 } }
  local beforeAdd, beforeRecalc = calls.add, calls.recalc
  local result = M.dispatch("spawn_reward", {
    reward = "trait:TemporaryDiscountTrait",
    requestId = "store-discount-add",
    includeCatalogs = false,
  })
  eq(result.lootObjectId, nil, "store trait leaked loot object id")
  eq(calls.add, beforeAdd + 1, "store trait did not mount")
  eq(calls.recalc, beforeRecalc + 1, "store duration recalculation did not run")
  eq(option.Processed, nil, "store option remained processed")
  check(type(option.ResourceCosts) == "table", "store option source costs were removed")
  check(type(option.DataOverrides) == "table", "store option overrides were not rebuilt")
  eq(option.DataOverrides.ResourceCosts, nil, "store option override costs were not invalidated")
end

-- IncreaseUsesOnStack extends the mounted owner instead of adding a duplicate.
do
  local existing = { Name = "TemporaryDiscountTrait", Id = 700, RemainingUses = 4 }
  resetTraits(existing)
  TraitData.TemporaryDiscountTrait.IncreaseUsesOnStack = true
  local beforeAdd, beforeUpdate = calls.add, calls.updateTrait
  M.dispatch("spawn_reward", {
    reward = "trait:TemporaryDiscountTrait",
    requestId = "store-discount-stack",
    includeCatalogs = false,
  })
  eq(calls.add, beforeAdd, "stacking store trait added a duplicate")
  eq(calls.updateTrait, beforeUpdate + 1, "stacking store trait did not refresh native number")
  eq(existing.RemainingUses, 6, "stacking store trait did not extend remaining uses")
  TraitData.TemporaryDiscountTrait.IncreaseUsesOnStack = false
end

-- ExtendedShopTrait turns only its allowlisted item into boss-duration state.
do
  local extension = {
    Name = "ExtendedShopTrait",
    Id = 701,
    ValidPermanentItemsLookup = { TemporaryDiscountTrait = true },
    BossExtension = 7,
    Activated = true,
  }
  resetTraits(extension)
  local beforeBoss = calls.useBossExtension
  M.dispatch("spawn_reward", {
    reward = "trait:TemporaryDiscountTrait",
    requestId = "store-discount-extended",
    includeCatalogs = false,
  })
  local added = CurrentRun.Hero.Traits[#CurrentRun.Hero.Traits]
  check(added ~= extension, "extended store trait did not add target")
  check(added.MakePermanent == true, "allowlisted store trait was not made permanent")
  check(added.UsesAsBosses == true, "extended store trait did not switch to boss duration")
  check(added.UsesAsEncounters == false and added.UsesAsRooms == false,
    "extended store trait kept ordinary duration modes")
  eq(added.RemainingUses, 7, "extended store trait ignored BossExtension")
  eq(calls.useBossExtension, beforeBoss + 1, "native BossExtension owner was not consumed")
end

-- Shop wrappers preserve native creation paths and return the spawned object id.
do
  local weapon = M.dispatch("spawn_reward", {
    reward = "WeaponUpgradeDrop",
    requestId = "shop-hammer",
    includeCatalogs = false,
  })
  eq(weapon.lootObjectId, 601, "Hammer wrapper object id")
  check(lastWeaponArgs.DoesNotBlockExit == true, "Hammer wrapper blocked room exit")

  local hermes = M.dispatch("spawn_reward", {
    reward = "ShopHermesUpgrade",
    requestId = "shop-hermes",
    includeCatalogs = false,
  })
  eq(hermes.lootObjectId, 602, "Hermes wrapper object id")
  check(lastHermesArgs.BoughtFromShop == true, "Hermes wrapper lost shop semantics")
  check(lastHermesLoot.CanReceiveGift == false, "Hermes wrapper kept gift interaction")

  local random = M.dispatch("spawn_reward", {
    reward = "RandomLoot",
    requestId = "shop-random",
    includeCatalogs = false,
  })
  eq(random.lootObjectId, 603, "random boon wrapper object id")
  eq(lastGiveArgs.ForceLootName, "ZeusUpgrade", "random boon wrapper ignored eligible source")
  check(lastGiveArgs.BoughtFromShop == true, "random boon wrapper lost shop semantics")
  check(lastGiveLoot.CanReceiveGift == false, "random boon wrapper kept gift interaction")

  local boosted = M.dispatch("spawn_reward", {
    reward = "BoostedRandomLoot",
    requestId = "shop-boosted-random",
    includeCatalogs = false,
  })
  eq(boosted.lootObjectId, 604, "boosted random boon object id")
  check(type(lastGiveArgs.BoonRaritiesOverride) == "table", "boosted random boon lost rarity override")
  eq(lastGiveArgs.BoonRaritiesOverride.Legendary, 0.1, "boosted Legendary weight")
  eq(lastGiveArgs.BoonRaritiesOverride.Epic, 0.25, "boosted Epic weight")
  eq(lastGiveArgs.BoonRaritiesOverride.Rare, 0.90, "boosted Rare weight")
  check(lastGiveLoot.BoonRaritiesOverride == lastGiveArgs.BoonRaritiesOverride,
    "boosted rarity override was not retained on loot")
end

-- TalentDrop remains a consumable while SpellDrop uses Selene's room-reward owner.
do
  local beforeConsumable = calls.consumable
  local talent = M.dispatch("spawn_reward", {
    reward = "TalentDrop",
    requestId = "selene-talent-drop",
    includeCatalogs = false,
  })
  eq(talent.lootObjectId, 501, "TalentDrop object id")
  eq(calls.consumable, beforeConsumable + 1, "TalentDrop did not use consumable owner")
  eq(lastConsumableArgs.name, "TalentDrop", "TalentDrop initialized wrong consumable")

  local beforeSpellConsumable = calls.consumable
  local spell = M.dispatch("spawn_reward", {
    reward = "SpellDrop",
    requestId = "selene-spell-drop",
    includeCatalogs = false,
  })
  eq(spell.lootObjectId, 605, "SpellDrop object id")
  eq(calls.consumable, beforeSpellConsumable, "SpellDrop fell through consumable owner")
  eq(lastRoomRewardArgs.RewardOverride, "SpellDrop", "SpellDrop lost native reward override")
  check(lastRoomRewardArgs.AutoLoadPackages == true, "SpellDrop lost package autoload")
end

-- Generic loot keeps package preparation and rejects unaudited setup events.
do
  local safe = M.dispatch("spawn_reward", {
    reward = "SpecialLoot",
    requestId = "generic-loot-safe",
    includeCatalogs = false,
  })
  eq(safe.lootObjectId, 606, "generic loot object id")
  check(packagePresent("SpecialPkg"), "required loot package was not loaded")
  check(packagePresent("ExtraPkg"), "GameData missing package was not loaded")
  eq(lastCreateLootArgs.Name, "SpecialLoot", "generic loot created wrong reward")
  check(lastCreateLootArgs.AutoLoadPackages == true, "generic loot lost package autoload")

  local beforeCreate = calls.createLoot
  expectError("Unsupported loot setup event: DangerousSetup", function()
    M.dispatch("spawn_reward", {
      reward = "UnsafeLoot",
      requestId = "generic-loot-unsafe",
      includeCatalogs = false,
    })
  end)
  eq(calls.createLoot, beforeCreate, "unsafe setup event reached CreateLoot")
end

print("hades2_store_reward_spawn_runtime_ok")
'''

with tempfile.TemporaryDirectory(prefix="mgt-store-reward-runtime-") as td:
    td = Path(td)
    harness = td / "store_reward_runtime.lua"
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
    assert "hades2_store_reward_spawn_runtime_ok" in proc.stdout, proc.stdout
    print(proc.stdout.strip())
