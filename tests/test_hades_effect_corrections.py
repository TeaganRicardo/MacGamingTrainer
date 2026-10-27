"""Native rank preservation and exact Patroclus effect acquisition contracts."""
import ast
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
sys.path.insert(0, str(ROOT / 'Backend'))
from lua_runtime_support import require_lua52
from games.hades.adapter import HadesAdapter
from games.hades.catalog import catalog, get_entry

module = ast.parse((ROOT / 'tests/test_hades_runtime.py').read_text())
fixture = next(ast.literal_eval(node.value) for node in module.body
               if isinstance(node, ast.Assign) and any(
                   isinstance(target, ast.Name) and target.id == 'harness' for target in node.targets))
fixture = fixture.split('\nlocal runtime = assert(load(SOURCE))()', 1)[0]
journey = r'''
local unit = CurrentRun.Hero
unit.dodgeChance = 0
function SetLifeProperty(args)
  assert(args.DestinationId == unit.ObjectId and args.Property == "DodgeChance"
    and args.ValueChangeType == "Add")
  unit.dodgeChance = unit.dodgeChance + args.Value
end
function SetUnitProperty(args)
  assert(args.DestinationId == unit.ObjectId and args.Property == "Speed"
    and args.ValueChangeType == "Multiply")
  unit.properties.Speed = unit.properties.Speed * args.Value
end
-- TraitScripts RemoveTraitData reverses earned dodge and speed on unequip.
local remove = RemoveTrait
function RemoveTrait(owner, name)
  for _, trait in pairs(owner.Traits) do
    if trait.Name == name and trait.AccumulatedDodgeBonus then
      SetLifeProperty({ DestinationId = owner.ObjectId, Property = "DodgeChance",
        Value = -trait.AccumulatedDodgeBonus, ValueChangeType = "Add" })
      SetUnitProperty({ DestinationId = owner.ObjectId, Property = "Speed",
        Value = 1 / (1 + trait.AccumulatedDodgeBonus), ValueChangeType = "Multiply" })
      break
    end
  end
  return remove(owner, name)
end
-- Native Keepsake data archetypes and AdvanceKeepsake's preserved fields.
for name, source in pairs({
    FastClearDodgeBonusTrait = { AccumulatedDodgeBonus = 0 },
    PerfectClearDamageBonusTrait = { AccumulatedDamageBonus = 1 },
    ForceZeusBoonTrait = { Uses = 1 },
}) do
  source.Name, source.Slot = name, "Keepsake"
  source.ChamberThresholds = { 25, 50 }
  source.RarityLevels = { Common = {}, Rare = {}, Epic = {} }
  TraitData[name] = source
end
-- AssistTrait rarity multiplies its BaseValue=1 remaining charge pool.
local processed = GetProcessedTraitData
local processedPatroclus = 0
function GetProcessedTraitData(args)
  if args.TraitName:find("Patroclus") or args.TraitName == "UpgradedTemporaryLastStandHealTrait" then
    processedPatroclus = processedPatroclus + 1
  end
  local result = processed(args)
  if result.Slot == "Assist" then result.RemainingUses = GetRarityValue(args.Rarity) end
  return result
end
local runtime = assert(load(SOURCE))()
local function selected(name)
  for _, trait in ipairs(runtime.status().traits) do if trait.name == name then return trait end end
  error("effect missing: " .. name)
end
local function actual(name)
  for _, trait in pairs(unit.Traits) do if trait.Name == name then return trait end end
  error("native effect missing: " .. name)
end
runtime.add_trait("FastClearDodgeBonusTrait", "Common", 1)
local feather = actual("FastClearDodgeBonusTrait")
feather.AccumulatedDodgeBonus, feather.Uses, feather.CurrentRoom = 0.18, 0, 8
SetLifeProperty({ DestinationId = unit.ObjectId, Property = "DodgeChance", Value = 0.18, ValueChangeType = "Add" })
SetUnitProperty({ DestinationId = unit.ObjectId, Property = "Speed", Value = 1.18, ValueChangeType = "Multiply" })
runtime.set_feature("moveSpeedMultiplier", 2)
for _, rarity in ipairs({ "Rare", "Epic", "Rare" }) do
  local before = selected("FastClearDodgeBonusTrait")
  runtime.update_trait(before.instanceId, rarity, 1)
  local updated = actual("FastClearDodgeBonusTrait")
  assert(updated.AccumulatedDodgeBonus == 0.18 and updated.Uses == 0 and updated.CurrentRoom == 8,
    "same-keepsake rank replacement discarded earned or consumed state")
  near(unit.dodgeChance, 0.18)
  near(unit.properties.Speed, 540 * 1.18 * 2)
  expectError("staleTrait", function() runtime.remove_trait(before.instanceId) end)
end
runtime.remove_trait(selected("FastClearDodgeBonusTrait").instanceId)
near(unit.dodgeChance, 0)
near(unit.properties.Speed, 540 * 2)
assert(GameState.LastAwardTrait == nil and GameState.KeepsakeChambers.FastClearDodgeBonusTrait == 25)
runtime.set_feature("moveSpeedMultiplier", 1)
runtime.add_trait("PerfectClearDamageBonusTrait", "Common", 1)
actual("PerfectClearDamageBonusTrait").AccumulatedDamageBonus = 1.32
runtime.update_trait(selected("PerfectClearDamageBonusTrait").instanceId, "Epic", 1)
near(GetTotalHeroTraitValue("AccumulatedDamageBonus"), 1.32)
-- Replacing with another Keepsake retains normal native teardown/defaults.
runtime.add_trait("ForceZeusBoonTrait", "Common", 1)
assert(not selected("ForceZeusBoonTrait").canExpire and actual("ForceZeusBoonTrait").Uses == 1)
assert(GetTraitNameCount(unit, "PerfectClearDamageBonusTrait") == 0)
local signet = actual("ForceZeusBoonTrait")
signet.Uses, signet.CurrentRoom = 0, 7
runtime.update_trait(selected("ForceZeusBoonTrait").instanceId, "Rare", 1)
assert(actual("ForceZeusBoonTrait").Uses == 0 and actual("ForceZeusBoonTrait").CurrentRoom == 7,
  "rank edit refreshed a consumed force-boon use or lost its room owner")
runtime.remove_trait(selected("ForceZeusBoonTrait").instanceId)

runtime.add_trait("FuryAssistTrait", "Rare", 1)
actual("FuryAssistTrait").RemainingUses = 1 -- one of two native charges consumed
runtime.update_trait(selected("FuryAssistTrait").instanceId, "Epic", 1)
assert(actual("FuryAssistTrait").RemainingUses == 2 and GameState.AssistUnlocks.FuryAssistTrait == 2,
  "Companion rank increase refilled spent charges instead of granting the native one added use")
runtime.update_trait(selected("FuryAssistTrait").instanceId, "Rare", 1)
assert(actual("FuryAssistTrait").RemainingUses == 1)
runtime.set_trait_uses(selected("FuryAssistTrait").instanceId, 0)
runtime.update_trait(selected("FuryAssistTrait").instanceId, "Common", 1)
assert(actual("FuryAssistTrait").RemainingUses == 0 and #unit.AssistWeapons == 1)
runtime.remove_trait(selected("FuryAssistTrait").instanceId)
assert(GameState.LastAssistTrait == nil and #unit.AssistWeapons == 0)

-- NPCData PatroclusBenefitChoices and Interactables PatroclusBuff's exact
-- synchronous acquisition body. Presentation wait is outside this one-shot.
PresetEventArgs.PatroclusBenefitChoices = {}
local expected = {
  TemporaryDoorHealTrait_Patroclus = { RemainingUses = 5, UsesAsRooms = true, DoorHeal = 0.3 },
  TemporaryImprovedWeaponTrait_Patroclus = { RemainingUses = 10, UsesAsEncounters = true,
    AddOutgoingDamageModifiers = { ValidWeaponMultiplier = 1.6 } },
  UpgradedTemporaryLastStandHealTrait = { RemainingUses = 15, UsesAsEncounters = true,
    LastStandHealFraction = 0.5 },
}
for name, source in pairs(expected) do
  source.Name = name
  TraitData[name] = source
  table.insert(PresetEventArgs.PatroclusBenefitChoices, {
    { PostLineThreadedFunctionName = "PatroclusBuff", PostLineFunctionArgs = { TraitName = name } },
  })
end
local acquire = AddTraitToHero
local nativeAcquisitions = 0
function AddTraitToHero(args)
  if expected[args.TraitData.Name] then
    assert(args.TraitData == TraitData[args.TraitData.Name], "Patroclus native trait initialization was replaced")
    nativeAcquisitions = nativeAcquisitions + 1
  end
  return acquire(args)
end
for name, source in pairs(expected) do
  local observed = runtime.add_trait(name, "Common", 1)
  local effect = selected(name)
  assert(effect.remainingUses == source.RemainingUses and effect.canExpire and effect.canSetUses)
  assert(actual(name).DoorHeal == source.DoorHeal
    and actual(name).LastStandHealFraction == source.LastStandHealFraction)
  if source.AddOutgoingDamageModifiers then
    assert(actual(name).AddOutgoingDamageModifiers.ValidWeaponMultiplier == 1.6)
  end
  assert(observed.heroReady)
  local count = #unit.Traits
  expectError("invalidValue", function() runtime.add_trait(name, "Common", 2) end)
  assert(#unit.Traits == count)
  runtime.remove_trait(effect.instanceId)
  expectError("staleTrait", function() runtime.remove_trait(effect.instanceId) end)
end
assert(nativeAcquisitions == 3 and processedPatroclus == 0 and #unit.Traits == 0)
runtime.disable_all()
near(unit.properties.Speed, 540)
print("hades_effect_corrections_native_journeys_ok")
'''
source = (ROOT / 'Backend/games/hades/runtime.lua').read_text()
result = subprocess.run([require_lua52('Hades effect review corrections'), '-e',
                         'local SOURCE=' + json.dumps(source) + '\n' + fixture + journey],
                        capture_output=True, text=True)
assert result.returncode == 0, result.stdout + '\n' + result.stderr
print(result.stdout.strip())

for identifier in ('TemporaryDoorHealTrait_Patroclus', 'TemporaryImprovedWeaponTrait_Patroclus',
                   'UpgradedTemporaryLastStandHealTrait'):
    params = {'trait': identifier, 'rarity': 'Common', 'level': 1}
    assert HadesAdapter._mutation_params('add_trait', params) == params
    entry = get_entry(identifier)
    for language in ('zh-CN', 'en'):
        assert identifier in {row['id'] for row in catalog(query=entry['names'][language])}
print('hades_effect_corrections_catalog_commands_ok')
