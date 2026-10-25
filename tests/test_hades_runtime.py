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
  savedState = { run = copy(CurrentRun), history = copy(GameState.RunHistory) }
  if saveFailure then error("native serializer failed") end
  return "saved", nil, 8
end
function UpdateHealthUI() updates.health = CurrentRun.Hero.Health end
function UpdateMoneyUI(value) updates.money = value end
function UpdateResourceUI(name, value) updates[name] = value end
function UpdateRerollUI(value) updates.rerolls = value end
GameState = { Resources = { MetaPoints = 17, Gems = 9 }, LifetimeResourcesGained = { MetaPoints = 200 }, RunHistory = {} }
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
  KeepsakeTrait = { Name = "KeepsakeTrait", Slot = "Keepsake", RarityLevels = { Common = {} } },
}
local nativeModifier = { Name = "NativeDamage", GlobalMultiplier = 1.3 }
local function newHero(id)
  return {
    ObjectId = id, Health = 30, MaxHealth = 100, InvulnerableFlags = { NativeMenu = true },
    Traits = {}, Weapons = { SwordWeapon = true }, OutgoingDamageModifiers = { copy(nativeModifier) },
    SuperMeter = 20, SuperMeterLimit = 100,
    properties = { Speed = 540, ClipSize = 2, ChargeTime = 2, Duration = 0.4 },
  }
end
CurrentRun = { Hero = newHero(10), Money = 100, NumRerolls = 3, InvulnerableFlags = { NativeMenu = true } }
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
end
function StopSuper() CurrentRun.Hero.SuperActive = false end
function PostEncounterDrainSuper() CurrentRun.Hero.SuperMeter = 0 end
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

local runtime = assert(load(SOURCE))()
assert(runtime.version == 1 and runtime.revision == 1 and runtime.generationId == tostring(runtime))
local firstHook = SetupHeroObject
assert(assert(load(SOURCE))() == runtime and SetupHeroObject == firstHook, "repeat load duplicated hooks")
for _, old in ipairs({ {}, { revision = 0 }, { revision = 2 } }) do
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
runtime.set_value("maxHealth", 60)
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
runtime.add_trait("KeepsakeTrait", "Common", 1)
assert(runtime.status().traits[1].limitation == "specialOwner")
RemoveWeaponTrait("KeepsakeTrait")
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
PostEncounterDrainSuper()
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
