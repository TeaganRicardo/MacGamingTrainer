"""Source-shaped combat, reroll permission and selected effect lifecycle journeys."""
import ast
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
sys.path.insert(0, str(ROOT / 'Backend'))
from lua_runtime_support import require_lua52
from core.adapter import AdapterError
from games.hades.adapter import HadesAdapter
from games.hades.preferences import HadesPreferenceStore
from games.hades.schema import DEFAULT_PREFERENCES

# Reuse the native-shaped engine fixture without importing/executing its tests.
module = ast.parse((ROOT / 'tests/test_hades_runtime.py').read_text())
fixture = next(ast.literal_eval(node.value) for node in module.body
               if isinstance(node, ast.Assign) and any(
                   isinstance(target, ast.Name) and target.id == 'harness' for target in node.targets))
fixture = fixture.split('\nlocal runtime = assert(load(SOURCE))()', 1)[0]
journey = r'''
local ammo = { RangedWeapon = 0, GunWeapon = 0 }
local ammoCalls = 0
CurrentRun.Hero.Weapons.RangedWeapon = true
CurrentRun.Hero.Weapons.GunWeapon = true
CurrentRun.CurrentRoom.LoadedAmmo = 2
CurrentRun.CurrentRoom.ValidVolleys = { native = true }
CurrentRun.Hero.StoredAmmo = { native = true }
function RunWeaponMethod(args)
  assert(args.Id == CurrentRun.Hero.ObjectId and args.Method == "RefillAmmo")
  ammoCalls = ammoCalls + 1
  ammo[args.Weapon] = 3
end
function UpdateAmmoUI(args) updates.castAmmo = args and args.Ammo or ammo.RangedWeapon end
function UpdateGunUI(args) updates.gunAmmo = args and args.Ammo or ammo.GunWeapon end
function AddIncomingDamageModifier(unit, modifier)
  unit.IncomingDamageModifiers = unit.IncomingDamageModifiers or {}
  table.insert(unit.IncomingDamageModifiers, modifier)
end
function Damage(victim, args)
  victim.Health = math.max(args.MinHealth or 0, victim.Health - args.DamageAmount)
  updates.damageRecorded = args.DamageAmount
end
function IncrementTraitCooldown(trait, increment)
  trait.CurrentCooldown = math.min(trait.CurrentCooldown + increment, trait.RoomCooldown or trait.TimeCooldown)
  if trait.ReactivateFunction then updates.reactivated = trait.Name end
end
local selected = { RerollMetaUpgrade = false, RerollPanelMetaUpgrade = false }
function IsMetaUpgradeSelected(name) return selected[name] or false end
function CreateBoonLootButtons(loot)
  local allowed = IsMetaUpgradeSelected("RerollPanelMetaUpgrade") and not loot.BlockReroll
  if loot.fail then error("native menu failure") end
  return allowed
end
CreateStoreButtons = function() return IsMetaUpgradeSelected("RerollPanelMetaUpgrade") end
CreateSellButtons = function() return IsMetaUpgradeSelected("RerollPanelMetaUpgrade") end
function RefreshUseButton(id, door) updates.door = door.CanBeRerolled end
function AssignRoomToExitDoor(door, room)
  door.Room = room
  if door.AllowReroll and not room.NoReroll and not room.Special and room.ChosenRewardType ~= "Shop"
      and IsMetaUpgradeSelected("RerollMetaUpgrade") then door.CanBeRerolled = true end
end
local runtime = assert(load(SOURCE))()
local unit = CurrentRun.Hero
runtime.set_feature("fullHealth", true)
assert(unit.Health == unit.MaxHealth and runtime.status().activeFeatures.fullHealth)
local args = { DamageAmount = 1000, MinHealth = 0 }
Damage(unit, args)
assert(unit.Health == unit.MaxHealth and updates.damageRecorded == 1000 and args.MinHealth == 0)
local enemy = { Health = 20 }
Damage(enemy, { DamageAmount = 5 })
assert(enemy.Health == 15, "life lock leaked to another unit")
runtime.set_feature("fullHealth", false)
Damage(unit, { DamageAmount = 10 })
assert(unit.Health == unit.MaxHealth - 10)
unit.IncomingDamageModifiers = { { Name = "NativeProtection", GlobalMultiplier = 0.7 } }
runtime.set_feature("incomingDamageMultiplier", 0.2)
assert(#unit.IncomingDamageModifiers == 2 and unit.IncomingDamageModifiers[2].GlobalMultiplier == 0.2)
Save()
assert(#savedState.run.Hero.IncomingDamageModifiers == 1 and #unit.IncomingDamageModifiers == 2,
  "temporary damage projection entered native save or was lost after saving")
runtime.set_feature("incomingDamageMultiplier", 1)
assert(unit.IncomingDamageModifiers[2] == nil and unit.IncomingDamageModifiers[1].Name == "NativeProtection")
runtime.set_feature("infiniteAmmo", true)
ammo.RangedWeapon, ammo.GunWeapon = 0, 0
UpdateAmmoUI({ Ammo = 0 }); UpdateGunUI({ Ammo = 0 })
assert(updates.castAmmo == 3 and updates.gunAmmo == 3)
assert(CurrentRun.CurrentRoom.LoadedAmmo == 2 and CurrentRun.CurrentRoom.ValidVolleys.native
  and unit.StoredAmmo.native, "ammo refill erased native projectile/load bookkeeping")
runtime.set_feature("infiniteAmmo", false)
local calls = ammoCalls
ammo.RangedWeapon = 0
UpdateAmmoUI({ Ammo = 0 })
assert(ammoCalls == calls and updates.castAmmo == 0)

assert(not CreateBoonLootButtons({}) and not IsMetaUpgradeSelected("RerollPanelMetaUpgrade"))
runtime.set_feature("forceRerolls", true)
assert(CreateBoonLootButtons({}) and CreateStoreButtons() and CreateSellButtons())
assert(not CreateBoonLootButtons({ BlockReroll = true }))
assert(not IsMetaUpgradeSelected("RerollPanelMetaUpgrade"), "permission changed Mirror selection")
local ok = pcall(CreateBoonLootButtons, { fail = true })
assert(not ok and not IsMetaUpgradeSelected("RerollPanelMetaUpgrade"), "native failure leaked permission")
local door = { ObjectId = 70, AllowReroll = true }
local room = { ChosenRewardType = "Boon" }
AssignRoomToExitDoor(door, room)
assert(door.CanBeRerolled)
local blocked = { ObjectId = 71, AllowReroll = true }
AssignRoomToExitDoor(blocked, { NoReroll = true })
assert(not blocked.CanBeRerolled)
Save()
assert(door.CanBeRerolled and not selected.RerollMetaUpgrade)
runtime.set_feature("forceRerolls", false)
assert(not door.CanBeRerolled and not CreateBoonLootButtons({}), "disable retained forced permissions")
runtime.set_feature("forceRerolls", true)
AssignRoomToExitDoor(door, room)
local replacement = { ChosenRewardType = "Boon" }
door.CanBeRerolled = false
AssignRoomToExitDoor(door, replacement)
assert(door.CanBeRerolled)
runtime.disable_all()
assert(not door.CanBeRerolled and door.Room == replacement, "door cleanup restored an old target")
selected.RerollMetaUpgrade = true
AssignRoomToExitDoor(door, room)
runtime.set_feature("forceRerolls", true)
runtime.disable_all()
assert(door.CanBeRerolled, "disable removed native Mirror permission")

TraitData.NativeCurse = { Name = "NativeCurse", RemainingUses = 3, UsesAsEncounters = true }
LootData.TrialUpgrade.PermanentTraits = { "ChaosTrait" }
LootData.TrialUpgrade.TemporaryTraits = { "NativeCurse" }
runtime.add_chaos_pair("ChaosTrait", "NativeCurse", "Epic", 4)
local curse = runtime.status().traits[1]
assert(curse.curse == "NativeCurse" and curse.blessing == "ChaosTrait"
  and curse.remainingUses == 4 and curse.canExpire and curse.canSetUses)
runtime.set_trait_uses(curse.instanceId, 2)
assert(runtime.status().traits[1].remainingUses == 2 and updates.trait == 2)
runtime.expire_trait(curse.instanceId)
local blessing = runtime.status().traits[1]
assert(blessing.name == "ChaosTrait" and blessing.rarity == "Epic" and blessing.canEdit)
expectError("staleTrait", function() runtime.expire_trait(curse.instanceId) end)
runtime.remove_trait(blessing.instanceId)
runtime.add_chaos_pair("ChaosTrait", "NativeCurse", "Rare", 3)
runtime.remove_trait(runtime.status().traits[1].instanceId)
assert(#unit.Traits == 0, "cancel granted the pending blessing")
local first = { Name = "TemporaryTrait", Id = "native-a", RemainingUses = 3 }
local second = { Name = "TemporaryTrait", Id = "native-b", RemainingUses = 2 }
unit.Traits = { first, second }
local effect = runtime.status().traits[1]
runtime.set_trait_uses(effect.instanceId, 5)
assert(first.RemainingUses == 5 and second.RemainingUses == 2)
runtime.remove_trait(effect.instanceId)
assert(#unit.Traits == 1 and unit.Traits[1] == second, "selected temporary effect removal crossed owners")
runtime.set_trait_uses(runtime.status().traits[1].instanceId, 0)
assert(#unit.Traits == 0)
TraitData.NativeCharge = { Name = "NativeCharge", Uses = 1, RoomCooldown = 3 }
local charged = { Name = "NativeCharge", Uses = 0, CurrentCooldown = 0, RoomCooldown = 3,
  ReactivateFunction = "NativeReactivate" }
unit.Traits = { charged }
effect = runtime.status().traits[1]
assert(effect.canSetUses and effect.canRefresh and not effect.canExpire and effect.remainingUses == 0)
runtime.set_trait_uses(effect.instanceId, 2)
assert(charged.Uses == 2)
runtime.set_trait_uses(effect.instanceId, 0)
assert(#unit.Traits == 1 and charged.Uses == 0, "zero native Uses removed the equipped effect")
runtime.refresh_trait(effect.instanceId)
assert(charged.CurrentCooldown == 3 and updates.reactivated == "NativeCharge")
runtime.remove_trait(effect.instanceId)

runtime.add_trait("ReincarnationTrait", "Rare", 1)
local equipped = runtime.status().traits[1]
assert(equipped.canEdit and equipped.canRemove)
runtime.update_trait(equipped.instanceId, "Epic", 1)
assert(GameState.KeepsakeChambers.ReincarnationTrait == 75)
runtime.remove_trait(runtime.status().traits[1].instanceId)
assert(GameState.LastAwardTrait == nil and GameState.KeepsakeChambers.ReincarnationTrait == 75)
assert(unit.MaxLastStands == 1 and #unit.LastStands == 1, "unequip lost native revival ownership")
unit.SuperMeter = 10
runtime.set_value("godGauge", 50)
assert(unit.SuperMeter == 50)
expectError("invalidValue", function() runtime.set_value("godGauge", 101) end)
CurrentRun = nil
runtime.configure({ fullHealth = true, forceRerolls = true, infiniteAmmo = true })
local dormant = runtime.status()
assert(dormant.features.fullHealth and not dormant.activeFeatures.fullHealth and not dormant.heroReady)
runtime.disable_all()
print("hades_combat_parity_journeys_ok")
'''
source = (ROOT / 'Backend/games/hades/runtime.lua').read_text()
result = subprocess.run([require_lua52('Hades combat parity'), '-e',
                         'local SOURCE=' + json.dumps(source) + '\n' + fixture + journey],
                        capture_output=True, text=True)
assert result.returncode == 0, result.stdout + '\n' + result.stderr
print(result.stdout.strip())

for params in ({'blessing': 'ChaosBlessingMeleeTrait', 'curse': 'ChaosCurseNoMoneyTrait',
                'rarity': 'Rare', 'encounters': 3},):
    assert HadesAdapter._mutation_params('add_chaos_pair', params) == params
for command, params in (
    ('add_chaos_pair', {'blessing': 'ZeusWeaponTrait', 'curse': 'ChaosCurseNoMoneyTrait', 'rarity': 'Rare', 'encounters': 3}),
    ('add_trait', {'trait': 'ChaosCurseNoMoneyTrait', 'rarity': 'Common', 'level': 1}),
    ('set_trait_uses', {'instanceId': 'effect:1', 'uses': -1}),
):
    try:
        HadesAdapter._mutation_params(command, params)
    except AdapterError:
        pass
    else:
        raise AssertionError((command, params))
with tempfile.TemporaryDirectory(prefix='hades-combat-preferences-') as directory:
    store = HadesPreferenceStore(Path(directory) / 'preferences.json')
    historical = {name: value for name, value in DEFAULT_PREFERENCES.items()
                  if name not in {'fullHealth', 'infiniteAmmo', 'forceRerolls', 'incomingDamageMultiplier'}}
    store.path.write_text(json.dumps({'schemaVersion': 1, 'features': historical}))
    assert store.load() == DEFAULT_PREFERENCES
    historical['unexpectedSetting'] = False
    store.path.write_text(json.dumps({'schemaVersion': 1, 'features': historical}))
    try:
        store.load()
    except AdapterError as error:
        assert error.code == 'preferences_failed'
    else:
        raise AssertionError('unknown preference field was silently accepted')
print('hades_combat_parity_contracts_ok')
