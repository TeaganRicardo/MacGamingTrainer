"""Hades-owned continuous intent, native coroutine lifetime and absolute edits."""
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
from lua_runtime_support import require_lua52

lua = require_lua52('Hades runtime feature journeys')
source = (ROOT / 'Backend/games/hades/runtime.lua').read_text()
harness = r'''
local function copy(value)
  if type(value) ~= "table" then return value end
  local result = {}
  for key, item in pairs(value) do result[key] = copy(item) end
  return result
end
local function near(actual, expected)
  assert(math.abs(actual - expected) < 0.00001, tostring(actual) .. " ~= " .. tostring(expected))
end
local function expectError(key, fn)
  local ok, message = pcall(fn)
  assert(not ok and tostring(message):find(key, 1, true), tostring(message))
end
local updates = {}
SaveIgnores = {}
local savedState, saveFailure
function Save()
  assert(SaveIgnores.MacGamingTrainerHades, "resident closures entered the native save")
  savedState = { run = copy(CurrentRun), history = copy(GameState.RunHistory), gameState = copy(GameState) }
  if saveFailure then error("native serializer failed") end
  return "saved", nil, 8
end
function UpdateHealthUI() updates.health = CurrentRun.Hero.Health end
function UpdateMoneyUI(value) updates.money = value end
function UpdateResourceUI(name, value) updates[name] = value end
function UpdateRerollUI(value) updates.rerolls = value end
function UpdateSuperMeterUI() updates.gauge = CurrentRun.Hero.SuperMeter end
GameState = { Resources = { MetaPoints = 17, Gems = 9 }, LifetimeResourcesGained = { MetaPoints = 200 }, RunHistory = {},
  KeepsakeChambers = {}, AssistUnlocks = {} }
WeaponSets = { HeroRushWeapons = { "RushWeapon", "RamWeapon" } }
TraitData = {
  HermesWeaponTrait = { PropertyChanges = {
    { WeaponNames = { "SwordWeapon" }, WeaponProperty = "ChargeTime", ChangeType = "Multiply", BaseValue = 0.7, ExcludeLinked = true },
    { WeaponNames = { "SwordWeapon" }, EffectName = "SwordDisableHeavy", EffectProperty = "Duration", ChangeType = "Multiply", BaseValue = 0.7 },
    { WeaponNames = { "SwordWeapon" }, ProjectileProperty = "StartFx2", ChangeType = "Absolute", ChangeValue = "HermesSwipe" },
  } },
  ZeusTrait = { Name = "ZeusTrait", Slot = "Melee", RarityLevels = { Common = {}, Rare = {}, Epic = {}, Heroic = {} } },
  AthenaTrait = { Name = "AthenaTrait", Slot = "Melee", RarityLevels = { Common = {}, Rare = {} } },
  PoseidonTrait = { Name = "PoseidonTrait", RarityLevels = { Common = {}, Rare = {}, Heroic = {} } },
  TemporaryTrait = { Name = "TemporaryTrait", RemainingUses = 3, RarityLevels = { Common = {} } },
  HammerTrait = { Name = "HammerTrait", Frame = "Hammer", RequiredWeapon = "SwordWeapon" },
  ChaosTrait = { Name = "ChaosTrait", RarityLevels = { Common = {}, Rare = {}, Epic = {} } },
  SetupTrait = { Name = "SetupTrait", SetupFunction = "NativeSetup", RarityLevels = { Common = {} } },
  LegendaryTrait = { Name = "LegendaryTrait", RarityLevels = { Legendary = {} } },
  DuoTrait = { Name = "DuoTrait", IsDuoBoon = true, Frame = "Duo", RarityLevels = { Legendary = {} } },
  KeepsakeTrait = { Name = "KeepsakeTrait", Slot = "Keepsake", ChamberThresholds = { 25, 50 },
    RarityLevels = { Common = {}, Rare = {}, Epic = {} } },
  ReincarnationTrait = { Name = "ReincarnationTrait", Slot = "Keepsake", ChamberThresholds = { 25, 50 },
    KeepsakeLastStandHealAmount = 50, RarityLevels = { Common = {}, Rare = {}, Epic = {} } },
  FuryAssistTrait = { Name = "FuryAssistTrait", Slot = "Assist", AddAssist = { WeaponName = "FuryAssistWeapon" },
    RarityLevels = { Common = {}, Rare = {}, Epic = {}, Heroic = {}, Legendary = {} },
    KeepsakeRarityGameStateRequirements = {
      { AssistUpgradeLevel = { Name = "FuryAssistTrait", Level = 0 } },
      { AssistUpgradeLevel = { Name = "FuryAssistTrait", Level = 1 } },
      { AssistUpgradeLevel = { Name = "FuryAssistTrait", Level = 2 } },
      { AssistUpgradeLevel = { Name = "FuryAssistTrait", Level = 3 } },
      { AssistUpgradeLevel = { Name = "FuryAssistTrait", Level = 4 } },
    } },
  OtherAssistTrait = { Name = "OtherAssistTrait", Slot = "Assist", AddAssist = { WeaponName = "OtherAssistWeapon" },
    RarityLevels = { Common = {} },
    KeepsakeRarityGameStateRequirements = { { AssistUpgradeLevel = { Name = "OtherAssistTrait", Level = 0 } } } },
  StoryKeepsakeTrait = { Name = "StoryKeepsakeTrait", Slot = "Keepsake", RarityLevels = { Common = {}, Rare = {} },
    KeepsakeRarityGameStateRequirements = { {}, { RequiredTextLines = { "StoryFlag" } } } },
}
local nativeModifier = { Name = "NativeDamage", GlobalMultiplier = 1.3 }
local function newHero(id)
  return {
    ObjectId = id, Health = 30, MaxHealth = 100, InvulnerableFlags = { NativeMenu = true },
    Traits = {}, Weapons = { SwordWeapon = true }, OutgoingDamageModifiers = { copy(nativeModifier) },
    SuperMeter = 20, SuperMeterLimit = 100,
    LastStands = { { Name = "NativeDeathDefiance" } }, MaxLastStands = 1,
    properties = { Speed = 540, ClipSize = 2, ChargeTime = 2, Duration = 0.4 },
  }
end
CurrentRun = { Hero = newHero(10), Money = 100, NumRerolls = 3, InvulnerableFlags = { NativeMenu = true }, CurrentRoom = {} }
function SetPlayerInvulnerable(flag)
  CurrentRun.Hero.InvulnerableFlags[flag] = true
  CurrentRun.InvulnerableFlags[flag] = true
end
function SetPlayerVulnerable(flag)
  CurrentRun.Hero.InvulnerableFlags[flag] = nil
  CurrentRun.InvulnerableFlags[flag] = nil
end
function AddOutgoingDamageModifier(unit, data) table.insert(unit.OutgoingDamageModifiers, data) end
function ApplyUnitPropertyChanges(unit, changes)
  for _, change in ipairs(changes) do
    local property = change.UnitProperty or change.WeaponProperty or change.EffectProperty
    local previous = unit.properties[property]
    assert(previous ~= nil, property)
    if change.ChangeType == "Multiply" then unit.properties[property] = previous * change.ChangeValue
    elseif change.ChangeType == "Add" then unit.properties[property] = previous + change.ChangeValue
    else error("unexpected property replacement") end
  end
end
-- Native SetupHeroObject clears protection each room and rebinds the native object.
function SetupHeroObject(run)
  run.Hero.ObjectId = run.Hero.ObjectId + 1
  run.Hero.InvulnerableFlags = {}
  run.InvulnerableFlags = {}
  run.Hero.properties = {
    Speed = 540 * (run.Hero.nativeMove or 1), ClipSize = 2 + (run.Hero.nativeDash or 0),
    ChargeTime = 2 * (run.Hero.nativeAttack or 1), Duration = 0.4 * (run.Hero.nativeAttack or 1),
  }
  return "room", nil, 7
end
-- SpendMoney follows RoomManager.lua:3261: native spend history remains independent of balance.
function SpendMoney(amount, source)
  if amount == nil or amount <= 0 then return end
  CurrentRun.Money = CurrentRun.Money - amount
  CurrentRun.MoneySpent = (CurrentRun.MoneySpent or 0) + amount
  UpdateMoneyUI(CurrentRun.Money)
  return "spent", nil, source
end
local rerollsSeenInMenu = {}
function AttemptBoonLootReroll()
  if CurrentRun.NumRerolls <= 0 then return end
  CurrentRun.NumRerolls = CurrentRun.NumRerolls - 1
  UpdateRerollUI(CurrentRun.NumRerolls)
  rerollsSeenInMenu[#rerollsSeenInMenu + 1] = CurrentRun.NumRerolls
end
function AttemptPanelReroll(screen, button)
  if CurrentRun.NumRerolls < button.Cost then return end
  CurrentRun.NumRerolls = CurrentRun.NumRerolls - button.Cost
  UpdateRerollUI(CurrentRun.NumRerolls)
  coroutine.yield("native-menu")
  CurrentRun.NumRerolls = CurrentRun.NumRerolls + 2
  return "panel", nil, 5
end
function AttemptReroll(run, target)
  if run.NumRerolls <= 0 or not target or not target.CanBeRerolled then return end
  run.NumRerolls = run.NumRerolls - 1
  UpdateRerollUI(run.NumRerolls)
  return "door"
end
function IsSuperValid() return CurrentRun.Hero.hasCall == true end
function BuildSuperMeter(run, amount)
  if not IsSuperValid() or run.Hero.SuperActive then return end
  run.Hero.SuperMeter = math.min(run.Hero.SuperMeter + amount, run.Hero.SuperMeterLimit, run.Hero.superCap or math.huge)
  UpdateSuperMeterUI()
end
function StopSuper() CurrentRun.Hero.SuperActive = false end
function thread() end
function wait(delay) coroutine.yield(delay) end
function IsSuperAvailable(unit) return unit.SuperMeter > 0 end
function PostEncounterDrainSuperPresentation() end
SuperUI = { PostEncounterDrainRates = { { Threshold = 0, Rate = 1 } } }
RoomThreadName = "RoomThread"
-- ShoutScripts.lua:274-301: a coroutine started before enabling the feature still calls global UI updates.
function PostEncounterDrainSuper()
  local elapsed = 0
  thread(PostEncounterDrainSuperPresentation, IsSuperAvailable(CurrentRun.Hero))
  while CurrentRun.Hero.SuperMeter > 0 and (CurrentRun.CurrentRoom.ChallengeEncounter == nil
      or not CurrentRun.CurrentRoom.ChallengeEncounter.InProgress) do
    local drainRate = 1
    for i, thresholdData in ipairs(SuperUI.PostEncounterDrainRates) do
      if elapsed >= thresholdData.Threshold and (SuperUI.PostEncounterDrainRates[i + 1] == nil
          or elapsed < SuperUI.PostEncounterDrainRates[i + 1].Threshold) then
        drainRate = 1 / thresholdData.Rate
        break
      end
    end
    CurrentRun.Hero.SuperMeter = CurrentRun.Hero.SuperMeter - 1
    UpdateSuperMeterUI()
    elapsed = elapsed + drainRate
    wait(drainRate, RoomThreadName)
  end
  if CurrentRun.Hero.SuperMeter < 0 then
    CurrentRun.Hero.SuperMeter = 0
    UpdateSuperMeterUI()
  end
end
function IsGodTrait(name) return name == "ZeusTrait" or name == "AthenaTrait" or name == "PoseidonTrait" end
function AreTraitsIdentical(a, b)
  if a.ForBoonInfo or b.ForBoonInfo then return false end
  if a == b then return true end
  if (a.LastCurseName and b.LastCurseName) or (a.LastBlessingName and b.LastBlessingName)
      or a.RemainingUses or b.RemainingUses then return a.Name == b.Name and a.Id == b.Id end
  return a.Name == b.Name
end
local setupCalls, healCalls = 0, 0
function NativeSetup() setupCalls = setupCalls + 1 end
function Heal(unit, args)
  assert(args.Silent and args.HealAmount >= 0)
  healCalls = healCalls + 1
  unit.Health = math.min(unit.MaxHealth, unit.Health + args.HealAmount)
end
function GetProcessedTraitData(args)
  local result = copy(TraitData[args.TraitName])
  -- Native ProcessTraitData only gives the first level an explicit rarity.
  if result.RarityLevels and result.RarityLevels[args.Rarity] then result.Rarity = args.Rarity end
  if result.KeepsakeLastStandHealAmount then
    result.KeepsakeLastStandHealAmount = result.KeepsakeLastStandHealAmount * ({ Common = 1, Rare = 1.5, Epic = 2 })[args.Rarity]
  end
  return result
end
function AddTraitToHero(args)
  local trait = args.TraitData or GetProcessedTraitData({ TraitName = args.TraitName, Rarity = args.Rarity })
  CurrentRun.Hero.Traits[#CurrentRun.Hero.Traits + 1] = copy(trait)
  if trait.SetupFunction then _G[trait.SetupFunction]() end
end
function EquipPlayerWeapon()
  CurrentRun.Hero.properties.ChargeTime = 3
  return "equipped"
end
function RemoveWeaponTrait(name)
  local unit = CurrentRun.Hero
  for index = #unit.Traits, 1, -1 do
    if unit.Traits[index].Name == name then table.remove(unit.Traits, index) end
  end
end

function GetRarityValue(rarity)
  for index, name in ipairs({ "Common", "Rare", "Epic", "Heroic", "Legendary" }) do
    if name == rarity then return index end
  end
  return 1
end
function GetRarityKey(index) return ({ "Common", "Rare", "Epic", "Heroic", "Legendary" })[index] end
function IsGameStateEligible(run, requirements)
  if requirements.AssistUpgradeLevel then
    local required = requirements.AssistUpgradeLevel
    return GameState.AssistUnlocks[required.Name] ~= nil and GameState.AssistUnlocks[required.Name] >= required.Level
  end
  return not requirements.RequiredTextLines
end
-- KeepsakeScripts.lua:1-29, 80-130: these owners also maintain permanent selection and revival state.
function GetKeepsakeLevel(traitName)
  local level = 1
  if TraitData[traitName].KeepsakeRarityGameStateRequirements then
    for i, requirements in ipairs(TraitData[traitName].KeepsakeRarityGameStateRequirements) do
      if IsGameStateEligible(CurrentRun, requirements) then level = i end
    end
    return level
  end
  if not GameState.KeepsakeChambers[traitName] or TraitData[traitName].ChamberThresholds == nil then return level end
  local threshold = 0
  for _, value in pairs(TraitData[traitName].ChamberThresholds) do
    threshold = threshold + value
    if threshold > GameState.KeepsakeChambers[traitName] then break end
    level = level + 1
  end
  return level
end
function AddTrait(unit, name, rarity)
  unit.Traits[#unit.Traits + 1] = GetProcessedTraitData({ Unit = unit, TraitName = name, Rarity = rarity })
end
function RemoveTrait(unit, name)
  for index, trait in ipairs(unit.Traits) do
    if trait.Name == name then
      table.remove(unit.Traits, index)
      for key, assist in ipairs(unit.AssistWeapons or {}) do
        if assist.TraitName == name then table.remove(unit.AssistWeapons, key); break end
      end
      return
    end
  end
end
function GetTotalHeroTraitValue(key)
  local value = 0
  for _, trait in pairs(CurrentRun.Hero.Traits) do value = value + (trait[key] or 0) end
  return value
end
function AddLastStand(args)
  local unit = args.Unit or CurrentRun.Hero
  if args.IncreaseMax then unit.MaxLastStands = (unit.MaxLastStands or 0) + 1 end
  table.insert(unit.LastStands, 1, args)
end
function RemoveLastStand(unit, name)
  for index, lastStand in pairs(unit.LastStands) do
    if lastStand.Name == name then table.remove(unit.LastStands, index); return end
  end
end
function EquipKeepsake(heroUnit, traitName, args)
  local unit = heroUnit or CurrentRun.Hero
  traitName = traitName or GameState.LastAwardTrait
  if traitName == nil then return end
  AddTrait(unit, traitName, GetRarityKey(GetKeepsakeLevel(traitName)), args)
  if not CurrentRun.Hero.IsDead then
    CurrentRun.TraitCache = CurrentRun.TraitCache or {}
    CurrentRun.TraitCache[traitName] = CurrentRun.TraitCache[traitName] or 1
  end
  if traitName == "ReincarnationTrait" then
    AddLastStand({ Name = "ReincarnationTrait", InsertAtEnd = true, IncreaseMax = true,
      Icon = "ExtraLifeSkelly", WeaponName = "LastStandReincarnateShield",
      HealAmount = GetTotalHeroTraitValue("KeepsakeLastStandHealAmount") })
  end
end
function UnequipKeepsake(heroUnit, traitName)
  local unit = heroUnit or CurrentRun.Hero
  RemoveTrait(unit, traitName)
  if traitName == "ReincarnationTrait" then
    RemoveLastStand(unit, "ReincarnationTrait")
    unit.MaxLastStands = unit.MaxLastStands - 1
  end
  if traitName == "HadesShoutKeepsake" then RemoveTrait(CurrentRun.Hero, "HadesShoutTrait") end
end
function EquipAssist(heroUnit, traitName, args)
  local unit = heroUnit or CurrentRun.Hero
  traitName = traitName or GameState.LastAssistTrait
  if traitName == nil then return end
  AddTrait(unit, traitName, GetRarityKey(GetKeepsakeLevel(traitName)), args)
end
function UnequipAssist(heroUnit, traitName) RemoveTrait(heroUnit or CurrentRun.Hero, traitName) end
function EquipReferencedWeapons(trait)
  if trait.AddAssist then CurrentRun.Hero.Weapons[trait.AddAssist.WeaponName] = true end
end
function AddAssistWeapons(unit, trait)
  if not trait.AddAssist then return end
  unit.AssistWeapons = unit.AssistWeapons or {}
  for _, data in pairs(unit.AssistWeapons) do if data.TraitName == trait.Name then return end end
  local assist = copy(trait.AddAssist)
  assist.TraitName = trait.Name
  table.insert(unit.AssistWeapons, assist)
end

local runtime = assert(load(SOURCE))()
assert(runtime.version == 1 and runtime.revision == 2 and runtime.generationId == tostring(runtime))
local firstHook = SetupHeroObject
assert(assert(load(SOURCE))() == runtime and SetupHeroObject == firstHook, "repeat load duplicated hooks")
for _, old in ipairs({ {}, { revision = 0 }, { revision = 1 }, { revision = 3 } }) do
  MacGamingTrainerHades = old
  expectError("hades.error.restartRequired", function() assert(load(SOURCE))() end)
end
MacGamingTrainerHades = runtime
local baseline = runtime.status()
assert(baseline.heroId == runtime.status().heroId and baseline.heroId:sub(1, #runtime.generationId) == runtime.generationId)
runtime.generationId = "fixture-generation"
assert(runtime.status().heroId:find("fixture-generation:", 1, true) == 1)
assert(baseline.heroReady and baseline.resources.MetaPoints == 17 and baseline.features.damageMultiplier == 1)
assert(runtime.json(baseline):find('"traits":[]', 1, true))
assert(runtime.json({ quote = '"\\\n', truth = true }):find('\\u000a', 1, true))

runtime.set_feature("invincibility", true)
assert(runtime.status().invincible and CurrentRun.InvulnerableFlags.NativeMenu)
runtime.set_feature("damageMultiplier", 3)
runtime.set_feature("moveSpeedMultiplier", 2)
runtime.set_feature("attackSpeedMultiplier", 4)
runtime.set_feature("dashBonus", 5)
local unit = CurrentRun.Hero
near(unit.properties.Speed, 1080)
near(unit.properties.ChargeTime, 0.5)
near(unit.properties.Duration, 0.1)
assert(unit.properties.ClipSize == 7)
assert(unit.OutgoingDamageModifiers[1].Name == "NativeDamage" and unit.OutgoingDamageModifiers[2].GlobalMultiplier == 3)
runtime.set_feature("moveSpeedMultiplier", 3)
near(unit.properties.Speed, 1620)
local a, b, c = SetupHeroObject(CurrentRun)
assert(a == "room" and b == nil and c == 7, "native return slots changed")
near(unit.properties.Speed, 1620)
near(unit.properties.ChargeTime, 0.5)
assert(unit.properties.ClipSize == 7 and runtime.status().invincible)
assert(EquipPlayerWeapon() == "equipped")
near(unit.properties.ChargeTime, 0.75)
-- Restore the new weapon's native charge time for the remaining fixtures.
unit.properties.ChargeTime = 0.5
assert(#unit.OutgoingDamageModifiers == 2, "duplicate Trainer damage modifier")
GameState.RunHistory = { CurrentRun }
local saveResult, absent, saveNumber = Save()
assert(saveResult == "saved" and absent == nil and saveNumber == 8)
assert(not savedState.run.InvulnerableFlags["MacGamingTrainer.Hades"])
assert(not savedState.run.Hero.InvulnerableFlags["MacGamingTrainer.Hades"])
assert(savedState.run.Hero.OutgoingDamageModifiers[2] == nil)
assert(savedState.run.Hero.OutgoingDamageModifiers[1].Name == "NativeDamage")
assert(savedState.run.Hero.InvulnerableFlags.NativeMenu == nil)
assert(runtime.status().invincible and unit.OutgoingDamageModifiers[2].GlobalMultiplier == 3)
saveFailure = true
expectError("native serializer failed", Save)
assert(runtime.status().invincible and unit.OutgoingDamageModifiers[2].GlobalMultiplier == 3)
saveFailure = false
GameState.RunHistory = {}

runtime.set_feature("moneyNoDecrease", true)
local spent, absent, source = SpendMoney(40, "shop")
assert(spent == "spent" and absent == nil and source == "shop")
assert(CurrentRun.Money == 100 and CurrentRun.MoneySpent == 40 and updates.money == 100)
CurrentRun.Money = CurrentRun.Money + 23
SpendMoney(20, "shop")
assert(CurrentRun.Money == 123 and CurrentRun.MoneySpent == 60)
SpendMoney(0, "nothing")
assert(CurrentRun.Money == 123)

runtime.set_feature("rerollsNoDecrease", true)
AttemptBoonLootReroll()
assert(CurrentRun.NumRerolls == 3 and rerollsSeenInMenu[1] == 3)
local panel = coroutine.create(function() return AttemptPanelReroll({}, { Cost = 2 }) end)
local ok, marker = coroutine.resume(panel)
assert(ok and marker == "native-menu" and CurrentRun.NumRerolls == 3, "native menu did not yield with its original lifetime")
AttemptBoonLootReroll()
assert(CurrentRun.NumRerolls == 3, "another callback consumed the suspended menu's lease")
local ok, result, absent, number = coroutine.resume(panel)
assert(ok and result == "panel" and absent == nil and number == 5)
assert(CurrentRun.NumRerolls == 5, "native gains were swallowed")
assert(AttemptReroll(CurrentRun, { CanBeRerolled = true }) == "door" and CurrentRun.NumRerolls == 5)
assert(AttemptReroll(CurrentRun, nil) == nil and CurrentRun.NumRerolls == 5)

unit.hasCall, unit.SuperMeter = true, 10
local existingDrain = coroutine.create(PostEncounterDrainSuper)
assert(coroutine.resume(existingDrain))
assert(unit.SuperMeter == 9)
runtime.set_feature("fullGodGauge", true)
assert(unit.SuperMeter == 100)
assert(coroutine.resume(existingDrain))
assert(unit.SuperMeter == 100 and updates.gauge == 100, "already-running native drain bypassed full gauge")
unit.SuperActive, unit.SuperMeter = true, 30
assert(coroutine.resume(existingDrain))
assert(unit.SuperMeter == 29 and updates.gauge == 29, "active Call's native drain was refilled")
unit.SuperActive, unit.SuperMeter = false, 0
runtime.set_feature("fullGodGauge", false)
assert(coroutine.resume(existingDrain) and coroutine.status(existingDrain) == "dead")
unit.hasCall, unit.SuperMeter = nil, 20
runtime.set_feature("fullGodGauge", true)
assert(unit.SuperMeter == 20, "unavailable Call was fabricated")
unit.hasCall = true
BuildSuperMeter(CurrentRun, 1)
assert(unit.SuperMeter == 100)
unit.SuperActive, unit.SuperMeter = true, 30
BuildSuperMeter(CurrentRun, 1)
assert(unit.SuperMeter == 30, "active native Call drain was overridden")
StopSuper()
assert(unit.SuperMeter == 100)
PostEncounterDrainSuper()
assert(unit.SuperMeter == 100)
unit.superCap, unit.SuperMeter = 25, 0
BuildSuperMeter(CurrentRun, 1)
assert(unit.SuperMeter == 25, "native Call cap was discarded")
unit.superCap = nil

runtime.set_value("health", 75)
unit.MaxHealth = 60
runtime.set_value("health", 60)
assert(unit.Health == 60 and unit.MaxHealth == 60 and updates.health == 60)
runtime.set_value("money", 7)
runtime.set_value("rerolls", 9)
assert(runtime.status().rerolls == 9 and updates.rerolls == 9)
runtime.set_value("rerolls", 5)
runtime.set_value("health", 10)
local healed = runtime.heal()
assert(healed.health == 60 and updates.health == 60 and healCalls == 1)
runtime.set_resource("MetaPoints", 55)
assert(CurrentRun.Money == 7 and GameState.Resources.MetaPoints == 55)
assert(GameState.LifetimeResourcesGained.MetaPoints == 200, "absolute resource edit fabricated earned history")
expectError("invalidValue", function() runtime.set_feature("moveSpeedMultiplier", 0) end)
expectError("invalidValue", function() runtime.set_feature("dashBonus", 1.5) end)
expectError("invalidValue", function() runtime.set_value("health", 0) end)
expectError("invalidValue", function() runtime.set_resource("Unknown", 10) end)

runtime.add_trait("ZeusTrait", "Rare", 1)
local traits = runtime.status().traits
assert(#traits == 1 and traits[1].canRemove and traits[1].canEdit and traits[1].rarity == "Rare")
local id = traits[1].instanceId
near(unit.properties.Speed, 1620)
near(unit.properties.ChargeTime, 0.5)
assert(unit.properties.ClipSize == 7, "trait acquisition stacked Trainer properties")
expectError("traitSlotOccupied", function() runtime.add_trait("AthenaTrait", "Rare", 1) end)
runtime.update_trait(id, "Heroic", 1)
local changed = runtime.status().traits[1]
assert(changed.instanceId ~= id and changed.rarity == "Heroic")
expectError("staleTrait", function() runtime.remove_trait(id) end)
runtime.remove_trait(changed.instanceId)
assert(#runtime.status().traits == 0)
near(unit.properties.Speed, 1620)
near(unit.properties.ChargeTime, 0.5)
assert(unit.properties.ClipSize == 7)
runtime.add_trait("PoseidonTrait", "Rare", 3)
traits = runtime.status().traits
assert(#traits == 1 and traits[1].level == 3 and traits[1].canEdit and traits[1].canRemove)
assert(unit.Traits[1].Rarity == "Rare" and unit.Traits[2].Rarity == nil and unit.Traits[3].Rarity == nil)
local level3Id = traits[1].instanceId
unit.Traits[1].AccumulatedFountainDamageBonus = 77
runtime.update_trait(level3Id, "Rare", 5)
traits = runtime.status().traits
assert(#traits == 1 and #unit.Traits == 5 and traits[1].level == 5 and traits[1].rarity == "Rare")
assert(traits[1].canEdit and traits[1].canRemove and unit.Traits[1].AccumulatedFountainDamageBonus == 77)
expectError("staleTrait", function() runtime.remove_trait(level3Id) end)
local level5Id = traits[1].instanceId
assert(runtime.status().traits[1].instanceId == level5Id)
runtime.update_trait(level5Id, "Heroic", 5)
traits = runtime.status().traits
assert(#traits == 1 and traits[1].level == 5 and traits[1].rarity == "Heroic" and traits[1].canRemove)
local rarityId = traits[1].instanceId
unit.Traits[5] = copy(unit.Traits[5])
expectError("staleTrait", function() runtime.remove_trait(rarityId) end)
runtime.remove_trait(runtime.status().traits[1].instanceId)
assert(#unit.Traits == 0 and #runtime.status().traits == 0)

for _, acquisition in ipairs({
  { "HammerTrait", "Common" }, { "ChaosTrait", "Epic" }, { "LegendaryTrait", "Legendary" }, { "DuoTrait", "Legendary" },
}) do
  runtime.add_trait(acquisition[1], acquisition[2], 1)
  local acquired = runtime.status().traits[1]
  assert(acquired.name == acquisition[1] and acquired.rarity == acquisition[2] and acquired.canEdit and acquired.canRemove)
  runtime.remove_trait(acquired.instanceId)
end
expectError("invalidValue", function() runtime.add_trait("LegendaryTrait", "Heroic", 1) end)
expectError("invalidValue", function() runtime.add_trait("HammerTrait", "Rare", 1) end)
runtime.add_trait("SetupTrait", "Common", 1)
assert(setupCalls == 1 and runtime.status().traits[1].limitation == "specialLifecycle")
expectError("unsupportedTrait", function() runtime.remove_trait(runtime.status().traits[1].instanceId) end)
RemoveWeaponTrait("SetupTrait")
runtime.add_trait("ZeusTrait", "Rare", 1)
local ordinaryBoon = runtime.status().traits[1].instanceId
runtime.add_trait("ReincarnationTrait", "Rare", 1)
assert(GameState.LastAwardTrait == "ReincarnationTrait" and GameState.KeepsakeChambers.ReincarnationTrait == 25)
assert(#unit.LastStands == 2 and unit.MaxLastStands == 2 and unit.LastStands[1].HealAmount == 75)
assert(unit.LastStands[2].Name == "NativeDeathDefiance")
assert(CurrentRun.TraitCache.ReincarnationTrait == 1)
local keepsakeId = runtime.status().traits[2].instanceId
GameState.KeepsakeChambers.ReincarnationTrait = 29
runtime.add_trait("ReincarnationTrait", "Rare", 1)
assert(#unit.LastStands == 2 and unit.MaxLastStands == 2 and runtime.status().traits[2].instanceId == keepsakeId)
assert(GameState.KeepsakeChambers.ReincarnationTrait == 29, "reselection reset native keepsake progress")
RemoveLastStand(unit, "ReincarnationTrait")
runtime.add_trait("ReincarnationTrait", "Rare", 1)
assert(#unit.LastStands == 1 and unit.MaxLastStands == 2, "reselection replenished a consumed Lucky Tooth")
expectError("invalidValue", function() runtime.add_trait("ReincarnationTrait", "Rare", 2) end)
runtime.add_trait("KeepsakeTrait", "Epic", 1)
assert(GameState.LastAwardTrait == "KeepsakeTrait" and GameState.KeepsakeChambers.KeepsakeTrait == 75)
assert(#unit.LastStands == 1 and unit.MaxLastStands == 1 and unit.LastStands[1].Name == "NativeDeathDefiance")
assert(runtime.status().traits[2].rarity == "Epic" and runtime.status().traits[2].limitation == "specialOwner")
assert(runtime.status().traits[1].instanceId == ordinaryBoon and unit.Weapons.SwordWeapon)
expectError("unsupportedTrait", function() runtime.add_trait("StoryKeepsakeTrait", "Rare", 1) end)
assert(GameState.LastAwardTrait == "KeepsakeTrait" and GameState.KeepsakeChambers.StoryKeepsakeTrait == nil)
runtime.add_trait("FuryAssistTrait", "Legendary", 1)
assert(GameState.LastAssistTrait == "FuryAssistTrait" and GameState.AssistUnlocks.FuryAssistTrait == 4)
assert(#unit.AssistWeapons == 1 and unit.AssistWeapons[1].TraitName == "FuryAssistTrait" and unit.Weapons.FuryAssistWeapon)
assert(GameState.LastAwardTrait == "KeepsakeTrait" and #unit.Traits == 3)
runtime.add_trait("FuryAssistTrait", "Legendary", 1)
assert(#unit.AssistWeapons == 1 and #unit.Traits == 3)
runtime.add_trait("OtherAssistTrait", "Common", 1)
assert(GameState.LastAssistTrait == "OtherAssistTrait" and GameState.AssistUnlocks.OtherAssistTrait == 0)
assert(#unit.AssistWeapons == 1 and unit.AssistWeapons[1].TraitName == "OtherAssistTrait")
assert(unit.Weapons.SwordWeapon and runtime.status().traits[1].instanceId == ordinaryBoon)
Save()
assert(savedState.run.Hero.AssistWeapons[1].TraitName == "OtherAssistTrait")
assert(savedState.gameState.LastAwardTrait == "KeepsakeTrait" and savedState.gameState.LastAssistTrait == "OtherAssistTrait")
assert(savedState.gameState.KeepsakeChambers.KeepsakeTrait == 75 and savedState.gameState.AssistUnlocks.OtherAssistTrait == 0)
-- RunManager.lua:251-252 re-equips the selected owners on a fresh run.
local previousHero = unit
CurrentRun.Hero = newHero(999)
EquipKeepsake(CurrentRun.Hero, GameState.LastAwardTrait)
EquipAssist(CurrentRun.Hero, GameState.LastAssistTrait)
assert(#CurrentRun.Hero.Traits == 2 and CurrentRun.Hero.Traits[1].Rarity == "Epic")
assert(CurrentRun.Hero.Traits[2].Name == "OtherAssistTrait")
CurrentRun.Hero = previousHero
UnequipKeepsake(unit, GameState.LastAwardTrait)
UnequipAssist(unit, GameState.LastAssistTrait)
GameState.LastAwardTrait, GameState.LastAssistTrait = nil, nil
runtime.remove_trait(ordinaryBoon)
runtime.add_trait("PoseidonTrait", "Rare", 1)
AddTraitToHero({ TraitName = "PoseidonTrait", Rarity = "Heroic" })
traits = runtime.status().traits
assert(#traits == 1 and traits[1].level == 2 and traits[1].limitation == "duplicateName")
expectError("unsupportedTrait", function() runtime.remove_trait(traits[1].instanceId) end)
assert(#unit.Traits == 2)
RemoveWeaponTrait("PoseidonTrait")
unit.Traits = {
  { Name = "TemporaryTrait", Id = "owner-a", RemainingUses = 3 },
  { Name = "TemporaryTrait", Id = "owner-b", RemainingUses = 3 },
}
traits = runtime.status().traits
assert(#traits == 2 and traits[1].level == 1 and traits[1].limitation == "duplicateName")
expectError("unsupportedTrait", function() runtime.remove_trait(traits[1].instanceId) end)
assert(#unit.Traits == 2, "name-based native removal crossed special owners")
unit.Traits = {}

unit.InvulnerableFlags.NativeScene, CurrentRun.InvulnerableFlags.NativeScene = true, true
unit.properties.Speed = unit.properties.Speed * 1.1
runtime.disable_all()
near(unit.properties.Speed, 594)
near(unit.properties.ChargeTime, 2)
near(unit.properties.Duration, 0.4)
assert(unit.properties.ClipSize == 2 and not runtime.status().invincible)
assert(unit.InvulnerableFlags.NativeScene and CurrentRun.InvulnerableFlags.NativeScene)
assert(unit.OutgoingDamageModifiers[1].Name == "NativeDamage" and unit.OutgoingDamageModifiers[2] == nil)
local normalDrain = coroutine.create(PostEncounterDrainSuper)
while coroutine.status(normalDrain) ~= "dead" do assert(coroutine.resume(normalDrain)) end
assert(unit.SuperMeter == 0)
SpendMoney(2, "normal")
assert(CurrentRun.Money == 5)
AttemptBoonLootReroll()
assert(CurrentRun.NumRerolls == 4)

runtime.set_feature("moveSpeedMultiplier", 2)
runtime.set_feature("invincibility", true)
CurrentRun.Hero = newHero(80)
CurrentRun.Hero.nativeMove, CurrentRun.Hero.nativeAttack, CurrentRun.Hero.nativeDash = 1.1, 0.8, 2
runtime.configure({ attackSpeedMultiplier = 4, dashBonus = 3 })
SetupHeroObject(CurrentRun)
near(CurrentRun.Hero.properties.Speed, 1188)
near(CurrentRun.Hero.properties.ChargeTime, 0.4)
assert(CurrentRun.Hero.properties.ClipSize == 7)
assert(runtime.status().invincible)
runtime.disable_all()
near(CurrentRun.Hero.properties.Speed, 594)
near(CurrentRun.Hero.properties.ChargeTime, 1.6)
assert(CurrentRun.Hero.properties.ClipSize == 4)
CurrentRun = nil
runtime.configure({ invincibility = true, moveSpeedMultiplier = 2 })
assert(not runtime.status().heroReady and runtime.status().features.invincibility)
runtime.set_feature("damageMultiplier", 3)
assert(runtime.status().features.damageMultiplier == 3)
expectError("invalidValue", function() runtime.configure({ invincibility = false, damageMultiplier = 0 }) end)
assert(runtime.status().features.invincibility and runtime.status().features.damageMultiplier == 3,
  "configure partially committed invalid desired intent")
expectError("heroNotReady", function() runtime.set_value("money", 10) end)
expectError("heroNotReady", runtime.heal)
CurrentRun = { Hero = newHero(10), Money = 0, NumRerolls = 0, InvulnerableFlags = {} }
SetupHeroObject(CurrentRun)
assert(runtime.status().invincible)
near(CurrentRun.Hero.properties.Speed, 1080)
assert(runtime.status().heroId ~= baseline.heroId)
CurrentRun = nil
runtime.disable_all()
assert(not runtime.status().features.invincibility)
print(runtime.json(runtime.status()))
print("hades_runtime_journeys_ok")
'''
proc = subprocess.run([lua, '-e', 'local SOURCE=' + json.dumps(source) + '\n' + harness], text=True, capture_output=True)
assert proc.returncode == 0, proc.stdout + '\n' + proc.stderr
lines = proc.stdout.splitlines()
state = json.loads(lines[-2])
assert state['heroReady'] is False and state['traits'] == [] and state['features']['moveSpeedMultiplier'] == 1
print(lines[-1])


# Exact supported-build Lua owners; engine calls and bookkeeping remain fixtures.
native_owners = r'''
-- Shipped UpgradeManager.lua SHA256 307a3521f37dba7a9ecff7080a13fd132f9338e4d16cdd04dbe47ddbda87ccee

function ApplyUnitPropertyChanges( unit, propertyChanges, applyLuaUpgrades, reverse )

	if propertyChanges == nil then
		return
	end

	for k, propertyChange in ipairs( propertyChanges ) do
		ApplyUnitPropertyChange( unit, propertyChange, applyLuaUpgrades, reverse )
	end
end

function ApplyUnitPropertyChange( unit, propertyChange, applyLuaUpgrades, reverse )
	if propertyChange.LegalUnits ~= nil then
		if not Contains( propertyChange.LegalUnits, unit.Name ) then
			return
		end
	elseif unit.SkipModifiers then
		return
	end

	if propertyChange.TraitName ~= nil then
		if not HeroHasTrait(propertyChange.TraitName) then
			return
		end
	end

	local changeValue = propertyChange.ChangeValue
	if reverse then
		if type(changeValue) == "number" then
			if propertyChange.ChangeType == "Multiply" then
				changeValue = 1 / changeValue
			elseif propertyChange.ChangeType == "Add" then
				changeValue = 0 - changeValue
			end
		elseif type(changeValue) == "boolean" then
			changeValue = not changeValue
		else
			return
		end
	end

	if propertyChange.ThingProperty ~= nil then
		SetThingProperty({ DestinationId = unit.ObjectId, Property = propertyChange.ThingProperty, Value = changeValue, ValueChangeType = propertyChange.ChangeType })
	end
	if propertyChange.LifeProperty ~= nil then
		ApplyLifePropertyChange( unit, propertyChange, changeValue )
	end
	if propertyChange.UnitProperty ~= nil then
		SetUnitProperty({ DestinationId = unit.ObjectId, Property = propertyChange.UnitProperty, Value = changeValue, ValueChangeType = propertyChange.ChangeType })
	end

	if applyLuaUpgrades and propertyChange.LuaProperty ~= nil and ( unit[propertyChange.LuaProperty] ~= nil or propertyChange.ChangeType == "Absolute" ) then
		local delta = nil
		if propertyChange.LuaProperty == "MaxHealth" and propertyChange.MaintainDelta and unit.Health ~= nil and unit.MaxHealth ~= nil then
			delta = changeValue
		end

		if propertyChange.LuaTable ~= nil then
			if propertyChange.ChangeType == "Absolute" then
				unit[propertyChange.LuaTable][propertyChange.LuaProperty] = changeValue
			elseif propertyChange.ChangeType == "Multiply" then
				unit[propertyChange.LuaTable][propertyChange.LuaProperty] = unit[propertyChange.LuaTable][propertyChange.LuaProperty] * changeValue
			elseif propertyChange.ChangeType == "Add" then
				unit[propertyChange.LuaTable][propertyChange.LuaProperty] = unit[propertyChange.LuaTable][propertyChange.LuaProperty] + changeValue
			elseif type(changeValue) == "boolean" then
				unit[propertyChange.LuaTable][propertyChange.LuaProperty] = not unit[propertyChange.LuaTable][propertyChange.LuaProperty]
			end
		else
			if propertyChange.ChangeType == "Absolute" then
				unit[propertyChange.LuaProperty] = changeValue
			elseif propertyChange.ChangeType == "Multiply" then
				unit[propertyChange.LuaProperty] = unit[propertyChange.LuaProperty] * changeValue
			elseif propertyChange.ChangeType == "Add" then
				unit[propertyChange.LuaProperty] = unit[propertyChange.LuaProperty] + changeValue
			elseif type(changeValue) == "boolean" then
				unit[propertyChange.LuaProperty] = not unit[propertyChange.LuaProperty]
			end
		end

		if propertyChange.LuaProperty == "MaxHealth" then
			if ( changeValue < 0 and propertyChange.ChangeType == "Add" ) or ( propertyChange.ChangeType == "Multiply" and changeValue < 1 ) then
				local currentHealth = unit.Health
				local maxHealth = unit.MaxHealth
				if currentHealth ~= nil and maxHealth ~= nil then

					if propertyChange.MaintainDelta then
						if propertyChange.ChangeType == "Add" then
							if delta < 0 then
								Damage( unit, { DamageAmount = math.abs(delta), MinHealth = 1, Silent = true, PureDamage = true } )
							else
								Heal( unit, { HealAmount = delta, SourceName = "MaxLifeChange", Silent = true})
							end
							currentHealth = math.max( 1, currentHealth + delta )
						else
							currentHealth = currentHealth * changeValue
							Damage( unit, { DamageAmount = math.abs(unit.Health - currentHealth), MinHealth = 1, Silent = true, PureDamage = true } )
						end
					end

					if currentHealth > maxHealth then
						unit.Health = maxHealth
					end
				end
			elseif not propertyChange.BlockHealing then
				if ( changeValue > 0 and propertyChange.ChangeType == "Add" ) then
					Heal( unit, { HealAmount = changeValue, Silent = true })
				elseif ( changeValue > 1 and propertyChange.ChangeType == "Multiply" ) then
					local currentHealth = unit.Health
					if currentHealth ~= nil then
						Heal( unit, { HealAmount = currentHealth * (changeValue - 1), Silent = true })
					end
				end
			end
		end
		if propertyChange.LuaProperty == "MaxHealth" or propertyChange.LuaProperty == "Health" then
			ValidateMaxHealth( propertyChange.BlockHealing )
			thread( UpdateHealthUI )
		end
		if propertyChange.LuaProperty == "SuperMeterLimit" or propertyChange.LuaProperty == "SuperCost" then
			DestroySuperMeter()
			ShowSuperMeter()
		end
	end

	if propertyChange.WeaponName ~= nil then
		ApplyWeaponPropertyChange( unit, propertyChange.WeaponName, propertyChange, reverse)
	end

	if propertyChange.WeaponNames ~= nil then
		for k, weaponName in pairs( propertyChange.WeaponNames ) do
			ApplyWeaponPropertyChange( unit, weaponName, propertyChange, reverse)
		end
	end

end

-- Shipped RoomManager.lua SHA256 ca379fe0708af778007aef929822e4cfe8cf3a47dd2a3d37bf57e582ddb1b924

function GetMaxHealthUpgradeIncrement( value )
	local expectedMaxHealth = HeroData.DefaultHero.MaxHealth
	for i, trait in pairs(CurrentRun.Hero.Traits) do
		if trait.PropertyChanges ~= nil then
			for k, propertyChange in pairs( trait.PropertyChanges ) do
				if propertyChange.LuaProperty == "MaxHealth" then
					expectedMaxHealth = expectedMaxHealth + propertyChange.ChangeValue
				end
			end
		end
	end

	expectedMaxHealth = expectedMaxHealth + GetNumMetaUpgrades("HealthMetaUpgrade") * MetaUpgradeData.HealthMetaUpgrade.ChangeValue + value
	expectedMaxHealth = round(expectedMaxHealth * GetTotalHeroTraitValue("MaxHealthMultiplier", { IsMultiplier = true }))

	return expectedMaxHealth - CurrentRun.Hero.MaxHealth
end

function ValidateMaxHealth( blockHealing )
	local expectedMaxHealth = HeroData.DefaultHero.MaxHealth
	for i, trait in pairs(CurrentRun.Hero.Traits) do
		if trait.PropertyChanges ~= nil then
			for k, propertyChange in pairs( trait.PropertyChanges ) do
				if propertyChange.LuaProperty == "MaxHealth" then
					expectedMaxHealth = expectedMaxHealth + propertyChange.ChangeValue
				end
			end
		end
	end
	expectedMaxHealth = expectedMaxHealth + GetNumMetaUpgrades("HealthMetaUpgrade") * MetaUpgradeData.HealthMetaUpgrade.ChangeValue
	expectedMaxHealth = round(expectedMaxHealth * GetTotalHeroTraitValue("MaxHealthMultiplier", { IsMultiplier = true }))
	if expectedMaxHealth ~= CurrentRun.Hero.MaxHealth then
		local delta = expectedMaxHealth - CurrentRun.Hero.MaxHealth
		CurrentRun.Hero.MaxHealth = round( CurrentRun.Hero.MaxHealth + delta )
		if not blockHealing then
			CurrentRun.Hero.Health = round( CurrentRun.Hero.Health + delta )
		end
	end
end

function AddMaxHealth( healthGained, source, args )
	args = args or {}
	if args.Thread then
		args.Thread = false
		thread( AddMaxHealth, healthGained, source, args )
		return
	end
	local startingHealth = CurrentRun.Hero.MaxHealth
	wait( args.Delay )
	healthGained = round(healthGained)
	local traitName = "RoomRewardMaxHealthTrait"
	if args.NoHealing then
		traitName = "RoomRewardEmptyMaxHealthTrait"
	end

	local healthTraitData = GetProcessedTraitData({ Unit = CurrentRun.Hero, TraitName = traitName })
	healthTraitData.PropertyChanges[1].ChangeValue = healthGained
	AddTraitToHero({ TraitData = healthTraitData })
	healthGained = round(healthGained * GetTotalHeroTraitValue("MaxHealthMultiplier", { IsMultiplier = true }))
	if not( args.Silent ) then
		MaxHealthIncreaseText({ MaxHealthGained = CurrentRun.Hero.MaxHealth - startingHealth , SpecialText = "MaxHealthIncrease" })
	end
end

-- Shipped TraitScripts.lua SHA256 473b3a2df05923bdbfe123e35047ff86ee44db4c7f4e3881e1812461d43ee3a6

function GetTotalHeroTraitValue(propertyName, args)
	args = args or {}
	local offset = 0
	local output = 0
	local hero = args.Hero or CurrentRun.Hero

	if args.IsMultiplier then
		offset = 1
		output = 1
	end

	for k, trait in pairs( hero.Traits ) do
		if trait[propertyName] ~= nil then
			output = output + (trait[propertyName] - offset)
		end
	end
	return output
end

function AddTraitToHero(args)
	local traitData = args.TraitData
	if traitData == nil then
		traitData = GetProcessedTraitData({ Unit = CurrentRun.Hero, TraitName = args.TraitName, Rarity = args.Rarity })
	end

	GameState.LastPickedTraitName = traitData.Name

	if not args.PreProcessedForDisplay then
		ExtractValues(CurrentRun.Hero, traitData, traitData)
	end

	if traitData.Slot and CurrentRun.CurrentRoom then
		CurrentRun.CurrentRoom.AcquiredSlot = traitData.Slot
	end
	-- traits may have information that acts on weapons, so we must first equip all associated weapons to the player
	EquipReferencedWeapons( traitData )
	AddTraitData( CurrentRun.Hero, traitData, args )

	EquipSpecialWeapons( CurrentRun.Hero, traitData )
	AddAssistWeapons( CurrentRun.Hero, traitData )
	for weaponName, v in pairs( CurrentRun.Hero.Weapons ) do
		AddWallSlamWeapons( CurrentRun.Hero, traitData )
		AddOnDamageWeapons(CurrentRun.Hero, weaponName, traitData)
		AddOnFireWeapons(CurrentRun.Hero, weaponName, traitData)
		if traitData.UpgradeHeroWeapon ~= nil and Contains(traitData.UpgradeHeroWeapon.WeaponNames, weaponName) then
			AddHeroWeaponUpgrade(weaponName, traitData.UpgradeHeroWeapon.UpgradeName)
		end
	end

	if ( traitData.EnemyPropertyChanges or traitData.AddEnemyOnDeathWeapons ) and ActiveEnemies ~= nil then
		for enemyId, enemy in pairs( ActiveEnemies ) do
			EquipReferencedEnemyWeapons( currentRun, traitData, enemy )
			ApplyEnemyTrait( CurrentRun, traitData, enemy )
		end
	end

	if traitData.AddShout then
		if traitData.AddShout.Cost then
			CurrentRun.Hero.SuperCost = traitData.AddShout.Cost
		else
			CurrentRun.Hero.SuperCost = 25
		end
		ShowSuperMeter()
	end
end

-- Shipped RoomPresentation.lua SHA256 2d164457578215cff1488d044d9c2826ec79fe2dd652445e58933beae4f69300

function DropHeroToRoomPosition( heroId, lightId, heroDestination, disableCollision, dropDelay, landDelay, speedAdjustment )
	AddInputBlock({ Name = "MoveHeroToRoomPosition" })
	AddTimerBlock( CurrentRun, "MoveHeroToRoomPosition" )
	wait( dropDelay )
	SetThingProperty({ DestinationId = CurrentRun.Hero.ObjectId, Property = "SuppressSounds", Value = true, DataValue = false })
	if disableCollision then
		SetUnitProperty({ DestinationId = heroId, Property = "CollideWithObstacles", Value = false })
	end
	if speedAdjustment then
		SetUnitProperty({ DestinationId = heroId, Property = "Speed", Value = speedAdjustment })
	end
	SetAlpha({ Id = heroId, Fraction = 1.0 })
	if( lightId ~= nil ) then
		SetAlpha({ Id = lightId, Fraction = 1.0 })
	end
	SetAnimation({ Name = "ZagreusHeroLanding_Air", DestinationId = heroId })
	SetThingProperty({ DestinationId = heroId, Property = "TouchdownGraphic", Value = "ZagreusHeroLanding_ReturnToIdle" })
	AdjustZLocation({ Id = heroId, Distance = 1500, Duration = 0 })
	wait(0.02)
	AdjustZLocation({ Id = heroId, Distance = 1500, Duration = 1.0 })
	Move({ Id = heroId, DestinationId = heroDestination, Mode = "Precise" })
	PlaySound({ Name = "/SFX/Player Sounds/ZagreusWhooshDropIn", Id = heroId, Delay = 0.5 })
	thread( DustLanding, 1.62 )
	wait( landDelay )
	Stop({ Id = heroId })
	AngleTowardTarget({ Id = heroId, DestinationId = 553377 })
	SetThingProperty({ DestinationId = CurrentRun.Hero.ObjectId, Property = "SuppressSounds", Value = false, DataValue = false })
	if disableCollision then
		SetUnitProperty({ DestinationId = heroId, Property = "CollideWithObstacles", Value = true })
	end
	if speedAdjustment then
		SetUnitProperty({ DestinationId = heroId, Property = "Speed", Value = 540 })
	end
	thread( DoRumble, { { ScreenPreWait = 0.02, LeftFraction = 0.2, Duration = 0.15 }, } )
	RemoveInputBlock({ Name = "MoveHeroToRoomPosition" })
	RemoveTimerBlock( CurrentRun, "MoveHeroToRoomPosition" )
end

function MoveHeroToRoomPosition( args )
	AddInputBlock({ Name = "MoveHeroToRoomPosition" })
	local heroId = CurrentRun.Hero.ObjectId

	local initialSpeed = GetUnitDataValue({ Id = heroId, Property = "Speed" })
	local defaultSpeed = 540
	if args.UseDefaultSpeed and initialSpeed ~= defaultSpeed then
		SetUnitProperty({ Property = "Speed", Value = defaultSpeed, DestinationId = heroId })
	end

	if args.DisableCollision then
		SetUnitProperty({ DestinationId = heroId, Property = "CollideWithObstacles", Value = false })
		SetUnitProperty({ DestinationId = heroId, Property = "CollideWithUnits", Value = false })
	end

	Move({ Id = heroId, DestinationId = args.DestinationId, SuccessDistance = args.NodeSuccessDistance or 32, StopAtEnd = true })
	local notifyName = "WithinDistance"..args.DestinationId

	NotifyWithinDistance({ Id = heroId, DestinationId = args.DestinationId, Distance = 45, Notify = notifyName, Timeout = args.Timeout or 5.0 })
	waitUntil( notifyName )
	Stop({ Id = heroId })
	if args.DisableCollision then
		SetUnitProperty({ DestinationId = heroId, Property = "CollideWithObstacles", Value = true })
		SetUnitProperty({ DestinationId = heroId, Property = "CollideWithUnits", Value = true })
	end

	if args.UseDefaultSpeed and initialSpeed ~= defaultSpeed then
		SetUnitProperty({ Property = "Speed", Value = initialSpeed, DestinationId = heroId })
		Halt({ Id = heroId })
	end

	if args.AngleTowardsIdOnEnd ~= nil then
		AngleTowardTarget({ Id = heroId, DestinationId = args.AngleTowardsIdOnEnd })
	end

	RemoveInputBlock({ Name = "MoveHeroToRoomPosition" })
end

function ResetPlayerMoveData( currentRun, initialSpeed, delay )
	wait(delay)
	SetUnitProperty({ Property = "StartGraphic", Value = "ZagreusStart", DestinationId = currentRun.Hero.ObjectId })
	SetUnitProperty({ Property = "MoveGraphic", Value = "ZagreusRun", DestinationId = currentRun.Hero.ObjectId })
	SetUnitProperty({ Property = "StopGraphic", Value = "ZagreusStop", DestinationId = currentRun.Hero.ObjectId })
	SetUnitProperty({ Property = "Speed", Value = initialSpeed, DestinationId = currentRun.Hero.ObjectId })
end

function SetupPlayerUnitInFlashback()
	SetUnitProperty({ Property = "StartGraphic", Value = nil, DestinationId = CurrentRun.Hero.ObjectId })
	SetUnitProperty({ Property = "MoveGraphic", Value = "ZagreusWalk", DestinationId = CurrentRun.Hero.ObjectId })
	SetUnitProperty({ Property = "StopGraphic", Value = "ZagreusWalkStop", DestinationId = CurrentRun.Hero.ObjectId })
	SetUnitProperty({ Property = "Speed", Value = 110, DestinationId = CurrentRun.Hero.ObjectId })
	SetThingProperty({ Property = "Graphic", Value = "ZagreusIdle", DestinationId = CurrentRun.Hero.ObjectId })
end

function RestorePlayerUnitAfterFlashback()
	SetThingProperty({ Property = "Graphic", Value = "ZagreusIdle", DestinationId = CurrentRun.Hero.ObjectId })
	SetUnitProperty({ Property = "StartGraphic", Value = "ZagreusStart", DestinationId = CurrentRun.Hero.ObjectId })
	SetUnitProperty({ Property = "MoveGraphic", Value = "ZagreusRun", DestinationId = CurrentRun.Hero.ObjectId })
	SetUnitProperty({ Property = "StopGraphic", Value = "ZagreusStop", DestinationId = CurrentRun.Hero.ObjectId })
	SetThingProperty({ Property = "Graphic", Value = "ZagreusIdle", DestinationId = CurrentRun.Hero.ObjectId })
	SetUnitProperty({ Property = "Speed", Value = 540, DestinationId = CurrentRun.Hero.ObjectId })
end

-- Shipped RunManager.lua SHA256 4b2fc24bee7e89f4cb9efedaafd7c35ef4829df6e047d4f37406f0619273895e

function AddTimerBlock( run, flag )
	if flag == nil then
		flag = "Generic"
	end
	run.BlockTimerFlags[flag] = true
end

function RemoveTimerBlock( run, flag )
	if flag == nil then
		flag = "Generic"
	end
	run.BlockTimerFlags[flag] = nil
end
'''
native_setup = r'''

-- Engine/bookkeeping stubs surround the unmodified native owner functions below.
HeroData = { DefaultHero = { MaxHealth = 50 } }
MetaUpgradeData = { HealthMetaUpgrade = { ChangeValue = 5 } }
function GetNumMetaUpgrades() return CurrentRun.Hero.metaHealth or 0 end
function round(value) return math.floor(value + 0.5) end
TraitData.RoomRewardMaxHealthTrait = { Name = "RoomRewardMaxHealthTrait", Hidden = true, PropertyChanges = {
  { LuaProperty = "MaxHealth", BaseValue = 25, ChangeType = "Add" },
} }
TraitData.RoomRewardEmptyMaxHealthTrait = { Name = "RoomRewardEmptyMaxHealthTrait", Hidden = true, PropertyChanges = {
  { LuaProperty = "MaxHealth", BaseValue = 25, ChangeType = "Add", BlockHealing = true },
} }
TraitData.HealthBonusTrait = { Name = "HealthBonusTrait", PropertyChanges = {
  { LuaProperty = "MaxHealth", ChangeValue = 20, ChangeType = "Add" },
} }
TraitData.SwordCursedLifeStealTrait = { Name = "SwordCursedLifeStealTrait", MaxHealthMultiplier = 0.4,
  PropertyChanges = { { LuaProperty = "MaxHealth", ChangeValue = 0.4, ChangeType = "Multiply" } },
}
local processedTrait = GetProcessedTraitData
function GetProcessedTraitData(args)
  local trait = processedTrait(args)
  for _, change in ipairs(trait.PropertyChanges or {}) do change.ChangeValue = change.ChangeValue or change.BaseValue end
  return trait
end
local engineObjects = {}
local function bind(unit) engineObjects[unit.ObjectId] = unit.properties end
local fixtureSetup = SetupHeroObject
function SetupHeroObject(run)
  local result = table.pack(fixtureSetup(run))
  bind(run.Hero)
  return table.unpack(result, 1, result.n)
end
function SetUnitProperty(args)
  if args.Property ~= "Speed" then return end
  local properties = assert(engineObjects[args.DestinationId])
  if args.ValueChangeType == "Multiply" then properties.Speed = properties.Speed * args.Value
  elseif args.ValueChangeType == "Add" then properties.Speed = properties.Speed + args.Value
  else properties.Speed = args.Value end
end
function GetUnitDataValue(args) return assert(engineObjects[args.Id])[args.Property] end
function UpdateHealthUI()
  assert(CurrentRun.Hero.MaxHealth >= 1 and CurrentRun.Hero.Health >= 0, "native health UI observed a negative vital")
  updates.health = CurrentRun.Hero.Health
end
function ExtractValues() end
function EquipSpecialWeapons() end
function AddWallSlamWeapons() end
function AddOnDamageWeapons() end
function AddOnFireWeapons() end
function AddTraitData(unit, trait, args)
  -- TraitScripts.lua:864,917-921: persistence precedes native property application.
  table.insert(unit.Traits, copy(trait))
  ApplyUnitPropertyChanges(unit, trait.PropertyChanges, true)
end
function thread(fn, ...) if fn == UpdateHealthUI then fn(...) end end
function SetThingProperty() end
function AddInputBlock() end
function RemoveInputBlock() end
function AddTimerBlock() end
function RemoveTimerBlock() end
function SetAlpha() end
function SetAnimation() end
function AdjustZLocation() end
function Move() end
function PlaySound() end
function Stop() end
function Halt() end
function AngleTowardTarget() end
function NotifyWithinDistance() end
function waitUntil(name) coroutine.yield(name) end
local pendingReset
function RoomEntranceHades(run)
  -- RoomPresentation.lua:560-582: native snapshot/scripted speed/restore lifetime.
  local initialSpeed = GetUnitDataValue({ Id = run.Hero.ObjectId, Property = "Speed" })
  SetUnitProperty({ DestinationId = run.Hero.ObjectId, Property = "Speed", Value = 130 })
  waitUntil("hades-entry")
  SetUnitProperty({ DestinationId = run.Hero.ObjectId, Property = "Speed", Value = initialSpeed })
  return "entrance", nil, 7
end
StartDeathLoopPresentation = RoomEntranceHades
function BedroomIntermissionApproach() return RoomEntranceHades(CurrentRun) end
local function surfaceEntry(run, room)
  -- RoomPresentation.lua:695-727,767-790: reset continues in its own coroutine.
  local initialSpeed = GetUnitDataValue({ Id = run.Hero.ObjectId, Property = "Speed" })
  SetUnitProperty({ DestinationId = run.Hero.ObjectId, Property = "Speed", Value = 115 })
  if room.WithReset then
    pendingReset = coroutine.create(function() ResetPlayerMoveData(run, initialSpeed, 2) end)
    assert(coroutine.resume(pendingReset))
  end
end
RoomEntranceE_Intro, RoomEntranceSurface = surfaceEntry, surfaceEntry
function ExitToHadesPresentation(run)
  SetUnitProperty({ DestinationId = run.Hero.ObjectId, Property = "Speed", Value = 130 })
end
function GardenScenePan()
  SetUnitProperty({ DestinationId = CurrentRun.Hero.ObjectId, Property = "Speed", Value = 115 })
end
local function finish(co)
  while coroutine.status(co) ~= "dead" do
    local result = table.pack(coroutine.resume(co))
    assert(result[1], result[2])
  end
end
local function nativeHeart(amount, noHealing)
  finish(coroutine.create(function() AddMaxHealth(amount, "RoomRewardMaxHealthDrop", { Silent = true, NoHealing = noHealing }) end))
end

'''
native_cases = r'''

CurrentRun.Hero.Health, CurrentRun.Hero.MaxHealth = 20, 50
CurrentRun.BlockTimerFlags = {}
bind(CurrentRun.Hero)
local initialLanding = coroutine.create(function()
  DropHeroToRoomPosition(CurrentRun.Hero.ObjectId, nil, 123, true, 1, 2, 50)
end)
assert(coroutine.resume(initialLanding))
local runtime = assert(load(SOURCE))()
local unit = CurrentRun.Hero
runtime.configure({ moveSpeedMultiplier = 1.25 })
near(unit.properties.Speed, 540)
assert(coroutine.resume(initialLanding))
near(unit.properties.Speed, 50)
finish(initialLanding)
near(unit.properties.Speed, 675)
runtime.disable_all()
near(unit.properties.Speed, 540)
unit.MaxHealth = 1000
runtime.set_value("maxHealth", 50)
assert(unit.MaxHealth == 50 and unit.Health == 20 and #unit.Traits == 0,
  "a zero-contribution edit left a stale maximum projection")
runtime.set_value("maxHealth", 1000)
assert(unit.MaxHealth == 1000 and unit.Health == 20, "an absolute maximum edit healed current health")
assert(unit.Traits[1].Name == "RoomRewardEmptyMaxHealthTrait" and unit.Traits[1].PropertyChanges[1].ChangeValue == 950)
nativeHeart(25)
assert(unit.MaxHealth == 1025 and unit.Health == 45, "a native heart discarded the edited maximum baseline")
ValidateMaxHealth()
assert(unit.MaxHealth == 1025 and unit.Health == 45)
local traitCount = #unit.Traits
runtime.set_value("maxHealth", 1025)
assert(#unit.Traits == traitCount, "an unchanged absolute edit added a reward")
runtime.set_value("maxHealth", 10)
assert(unit.MaxHealth == 10 and unit.Health == 10, "a decreased maximum did not clamp current health")
nativeHeart(25)
assert(unit.MaxHealth == 35 and unit.Health == 35)
AddTraitToHero({ TraitName = "HealthBonusTrait" })
assert(unit.MaxHealth == 55 and unit.Health == 55, "native trait acquisition discarded the edited baseline")
AddTraitToHero({ TraitName = "SwordCursedLifeStealTrait" })
runtime.set_value("maxHealth", 1)
assert(unit.MaxHealth == 1 and unit.Health == 1, "a curse multiplier made a decreased maximum negative")
runtime.set_value("maxHealth", 1001)
assert(unit.MaxHealth == 1001 and unit.Health == 1)
nativeHeart(25)
assert(unit.MaxHealth == 1011 and unit.Health == 11, "native multiplier semantics changed after the edit")
unit.metaHealth = 3
ValidateMaxHealth()
assert(unit.MaxHealth == 1017 and unit.Health == 17, "native mirror recomputation lost the run contribution")
runtime.set_feature("invincibility", true)
runtime.set_feature("damageMultiplier", 3)
runtime.disable_all()
assert(unit.MaxHealth == 1017 and unit.Health == 17, "Disable All reverted a committed numeric edit")
Save()
for _, trait in pairs(savedState.run.Hero.Traits) do
  assert(TraitData[trait.Name], "numeric persistence requires a Trainer-only trait definition")
end
assert(savedState.run.Hero.InvulnerableFlags["MacGamingTrainer.Hades"] == nil)
local liveRun = CurrentRun
CurrentRun = copy(savedState.run)
CurrentRun.Hero.MaxHealth = 1
ValidateMaxHealth(true)
assert(CurrentRun.Hero.MaxHealth == 1017 and CurrentRun.Hero.Health == 17,
  "native recomputation of the saved run required Trainer state")
CurrentRun = liveRun

-- An engine landing writes an absolute 540 after yielding. Trainer ownership
-- begins before that native lifetime and resumes after its final write.
runtime.configure({ moveSpeedMultiplier = 1.25 })
near(unit.properties.Speed, 675)
local landing = coroutine.create(function() DropHeroToRoomPosition(unit.ObjectId, nil, 123, true, 1, 2, 50) end)
local ok, delay = coroutine.resume(landing)
assert(ok and delay == 1)
near(unit.properties.Speed, 540)
ok, delay = coroutine.resume(landing)
assert(ok and delay == 0.02)
near(unit.properties.Speed, 50)
runtime.configure({ moveSpeedMultiplier = 2 })
near(unit.properties.Speed, 50)
finish(landing)
near(unit.properties.Speed, 1080)
runtime.disable_all()
near(unit.properties.Speed, 540)

runtime.configure({ moveSpeedMultiplier = 1.25 })
local moving = coroutine.create(function() MoveHeroToRoomPosition({ DestinationId = 456, UseDefaultSpeed = true }) end)
ok, delay = coroutine.resume(moving)
assert(ok and delay == "WithinDistance456")
near(unit.properties.Speed, 540)
runtime.disable_all()
finish(moving)
near(unit.properties.Speed, 540)

unit.properties.Speed = 594
runtime.configure({ moveSpeedMultiplier = 1.25 })
near(unit.properties.Speed, 742.5)
moving = coroutine.create(function() MoveHeroToRoomPosition({ DestinationId = 457, UseDefaultSpeed = true }) end)
assert(coroutine.resume(moving))
near(unit.properties.Speed, 540)
runtime.disable_all()
finish(moving)
near(unit.properties.Speed, 594)
unit.properties.Speed = 540

runtime.configure({ moveSpeedMultiplier = 1.25 })
local firstMove = coroutine.create(function() MoveHeroToRoomPosition({ DestinationId = 458, UseDefaultSpeed = true }) end)
local secondMove = coroutine.create(function() MoveHeroToRoomPosition({ DestinationId = 459, UseDefaultSpeed = true }) end)
assert(coroutine.resume(firstMove))
assert(coroutine.resume(secondMove))
runtime.configure({ moveSpeedMultiplier = 2 })
finish(firstMove)
near(unit.properties.Speed, 540)
finish(secondMove)
near(unit.properties.Speed, 1080)
runtime.disable_all()
near(unit.properties.Speed, 540)

runtime.configure({ moveSpeedMultiplier = 1.25 })
local entrance = coroutine.create(function()
  local a, b, c = RoomEntranceHades(CurrentRun)
  assert(a == "entrance" and b == nil and c == 7, "movement wrapper changed native return slots")
end)
assert(coroutine.resume(entrance))
near(unit.properties.Speed, 130)
runtime.disable_all()
near(unit.properties.Speed, 130)
finish(entrance)
near(unit.properties.Speed, 540)

runtime.configure({ moveSpeedMultiplier = 1.25 })
RoomEntranceSurface(CurrentRun, { WithReset = true })
near(unit.properties.Speed, 115)
runtime.disable_all()
near(unit.properties.Speed, 115)
finish(pendingReset)
near(unit.properties.Speed, 540)

runtime.configure({ moveSpeedMultiplier = 1.25 })
SetupPlayerUnitInFlashback()
near(unit.properties.Speed, 110)
runtime.configure({ moveSpeedMultiplier = 2 })
near(unit.properties.Speed, 110)
RestorePlayerUnitAfterFlashback()
near(unit.properties.Speed, 1080)
runtime.disable_all()
near(unit.properties.Speed, 540)

runtime.configure({ moveSpeedMultiplier = 1.25 })
RoomEntranceE_Intro(CurrentRun, {})
near(unit.properties.Speed, 115)
runtime.disable_all()
near(unit.properties.Speed, 115)
SetupHeroObject(CurrentRun)
near(unit.properties.Speed, 540)
runtime.configure({ moveSpeedMultiplier = 1.25 })
ExitToHadesPresentation(CurrentRun)
near(unit.properties.Speed, 130)
SetupHeroObject(CurrentRun)
near(unit.properties.Speed, 675)
runtime.disable_all()
near(unit.properties.Speed, 540)

runtime.configure({ moveSpeedMultiplier = 1.25 })
local oldRun, oldUnit = CurrentRun, unit
landing = coroutine.create(function() DropHeroToRoomPosition(oldUnit.ObjectId, nil, 123, true, 1, 2, 50) end)
assert(coroutine.resume(landing))
CurrentRun = { Hero = newHero(800), Money = 0, NumRerolls = 0, InvulnerableFlags = {}, CurrentRoom = {}, BlockTimerFlags = {} }
bind(CurrentRun.Hero)
SetupHeroObject(CurrentRun)
near(CurrentRun.Hero.properties.Speed, 675)
finish(landing)
near(CurrentRun.Hero.properties.Speed, 675)
near(oldUnit.properties.Speed, 540)
runtime.disable_all()
near(CurrentRun.Hero.properties.Speed, 540)
print("hades_runtime_native_max_health_and_movement_ok")

'''
native_harness = harness.split('\nlocal runtime = assert(load(SOURCE))()', 1)[0] + native_setup + native_owners + native_cases
proc = subprocess.run([lua, '-e', 'local SOURCE=' + json.dumps(source) + '\n' + native_harness], text=True, capture_output=True)
assert proc.returncode == 0, proc.stdout + '\n' + proc.stderr
assert proc.stdout.strip() == 'hades_runtime_native_max_health_and_movement_ok', proc.stdout
print(proc.stdout.strip())
