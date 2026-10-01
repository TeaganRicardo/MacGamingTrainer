"""Resident behavior test for seamless Cast recast across delivery shapes.

The recast gate is a per-weapon engine property.  The target build swaps the
fired cast weapon when a cast-shape boon is owned, so overriding only the base
``WeaponCast`` leaves the fired variant's own gate in force and the recast stays
blocked for thrown/transformed casts.  This test drives the resident runtime
with a mocked weapon layer and asserts the gate follows the resolved delivery
weapon, restores native values when the modifier is removed or the feature is
disabled, and fails closed when a variant write is rejected.

Reproduction order matters: this is the RED fixture for the defect.  Before the
fix the variant assertions fail because only ``WeaponCast`` was gated.
"""

import shutil
import subprocess
import tempfile
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "Backend/games/hades2/runtime/hades.lua"
LUA = shutil.which("lua5.2")

if not LUA:
    raise SystemExit("lua5.2 is required for cast recast runtime behavior tests")

HARNESS = r'''
local runtimePath = assert(arg[1], "runtime path required")

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

-- Engine weapon layer.  The gate properties are per weapon, exactly as the
-- target build's native binary consumes them.
local CAST_PROPERTIES = {
  "IgnoreOwnerAttackDisabled", "Cooldown", "AllowMultiFireRequest", "IgnoreForceCooldown", "ActiveProjectileCap",
}
local NATIVE = {
  WeaponCast = { IgnoreOwnerAttackDisabled = false, Cooldown = 0.75, AllowMultiFireRequest = false, IgnoreForceCooldown = false, ActiveProjectileCap = 1 },
  WeaponCastProjectile = { IgnoreOwnerAttackDisabled = false, Cooldown = 0.60, AllowMultiFireRequest = false, IgnoreForceCooldown = false, ActiveProjectileCap = 1 },
  WeaponCastProjectileHades = { IgnoreOwnerAttackDisabled = false, Cooldown = 0.60, AllowMultiFireRequest = false, IgnoreForceCooldown = false, ActiveProjectileCap = 1 },
  WeaponAnywhereCast = { IgnoreOwnerAttackDisabled = false, Cooldown = 0.60, AllowMultiFireRequest = false, IgnoreForceCooldown = false, ActiveProjectileCap = 1 },
  WeaponCastLob = { IgnoreOwnerAttackDisabled = false, Cooldown = 0.60, AllowMultiFireRequest = false, IgnoreForceCooldown = false, ActiveProjectileCap = 1 },
}
local live = {}
for weaponName, values in pairs(NATIVE) do
  live[weaponName] = {}
  for _, property in ipairs(CAST_PROPERTIES) do live[weaponName][property] = values[property] end
end
local failWeaponWrite = nil
local weaponWrites = 0

GetWeaponDataValue = function(args)
  local weapon = live[args.WeaponName]
  if weapon == nil then return nil end
  return weapon[args.Property]
end
GetBaseDataValue = function(args)
  if args.Type ~= "Weapon" then return nil end
  local values = NATIVE[args.Name]
  if values == nil then return nil end
  return values[args.Property]
end
SetWeaponProperty = function(args)
  weaponWrites = weaponWrites + 1
  if failWeaponWrite ~= nil and args.WeaponName == failWeaponWrite then
    error("synthetic engine rejection for " .. args.WeaponName)
  end
  local weapon = live[args.WeaponName]
  if weapon == nil then return end
  weapon[args.Property] = args.Value
end
SetEffectProperty = function(args)
  return true
end

dofile(runtimePath)
local M = assert(__MacGamingTrainerV1, "resident runtime did not initialize")

-- Production LLDB calls serialize dispatch results before returning them to the
-- backend. Exercise that boundary explicitly so diagnostics cannot hide values
-- that are valid Lua tables but invalid under the resident JSON contract.
local encodedStatus = M.json(M.dispatch("status", {}))
if type(encodedStatus) ~= "string" or encodedStatus == "" then
  error("ASSERTION FAILED: status JSON boundary did not produce encoded output", 0)
end

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

local function setTraits(...)
  CurrentRun.Hero.Traits = { ... }
  CurrentRun.Hero.TraitDictionary = {}
  for _, trait in ipairs(CurrentRun.Hero.Traits) do
    if trait.Name then CurrentRun.Hero.TraitDictionary[trait.Name] = true end
  end
end
local function modifier(name, weaponName)
  return { Name = name, PreEquipWeapons = { weaponName }, Rarity = "Common", StackNum = 1 }
end
local function gateOf(weaponName, property)
  return live[weaponName][property]
end
local function nativeOf(weaponName, property)
  return NATIVE[weaponName][property]
end
local function assertGated(weaponName, label)
  for _, property in ipairs(CAST_PROPERTIES) do
    local expected = ({ IgnoreOwnerAttackDisabled = true, Cooldown = 0, AllowMultiFireRequest = true, IgnoreForceCooldown = true, ActiveProjectileCap = 32 })[property]
    eq(gateOf(weaponName, property), expected, label .. " " .. weaponName .. "." .. property)
  end
end
local function assertNative(weaponName, label)
  for _, property in ipairs(CAST_PROPERTIES) do
    eq(gateOf(weaponName, property), nativeOf(weaponName, property), label .. " " .. weaponName .. "." .. property)
  end
end
local function castRuntime()
  local state = M.dispatch("status", {})
  return state.runtimeDiagnostics.castRuntime
end

-- A: base cast.  No cast-shape modifier is owned, so only WeaponCast is the
-- delivery weapon and only WeaponCast is gated.
do
  setTraits()
  M.dispatch("set_feature", { feature = "instantCastCooldown", value = true })
  assertGated("WeaponCast", "base gate")
  assertNative("WeaponCastProjectile", "unowned variant must stay native")
end

-- B: Hestia's thrown cast (CastProjectileBoon -> WeaponCastProjectile).  This is
-- the user's first named example.  Acquiring the modifier must re-target the
-- gate onto the weapon that is now actually fired.  This is the RED assertion
-- for the defect: before the fix only WeaponCast was gated.
do
  setTraits(modifier("CastProjectileBoon", "WeaponCastProjectile"))
  M.dispatch("status", {})
  assertGated("WeaponCast", "thrown cast base gate")
  assertGated("WeaponCastProjectile", "thrown cast delivery gate")
end

-- C: Hades' attached cast (HadesCastProjectileBoon -> WeaponCastProjectileHades).
-- This is the user's second named example.  The previous variant is no longer
-- the delivery weapon and must be restored to its native gate.
do
  setTraits(modifier("HadesCastProjectileBoon", "WeaponCastProjectileHades"))
  M.dispatch("status", {})
  assertGated("WeaponCastProjectileHades", "attached cast delivery gate")
  assertNative("WeaponCastProjectile", "replaced variant must be restored")
end

-- D: removing the modifier restores native behavior without toggling the
-- feature, and disabling restores every gated weapon.
do
  setTraits()
  M.dispatch("status", {})
  assertNative("WeaponCastProjectileHades", "modifier removal restore")

  setTraits(modifier("CastAnywhereBoon", "WeaponAnywhereCast"))
  M.dispatch("status", {})
  assertGated("WeaponAnywhereCast", "transformed cast delivery gate")

  M.dispatch("set_feature", { feature = "instantCastCooldown", value = false })
  assertNative("WeaponCast", "disable restore base")
  assertNative("WeaponAnywhereCast", "disable restore variant")
end

-- E: a rejected variant write must fail closed.  The feature must not report
-- itself active, and no half-applied override may leak into the run.
do
  setTraits(modifier("CastProjectileBoon", "WeaponCastProjectile"))
  failWeaponWrite = "WeaponCastProjectile"
  local beforeWrites = weaponWrites
  expectError("Feature unavailable", function()
    M.dispatch("set_feature", { feature = "instantCastCooldown", value = true })
  end)
  check(weaponWrites > beforeWrites, "variant write was never attempted")
  eq(M.desiredFeatures.instantCastCooldown, false, "failed feature stayed desired")
  assertNative("WeaponCast", "failed install leaked base override")
  assertNative("WeaponCastProjectile", "failed install leaked variant override")
  failWeaponWrite = nil
end

-- F: the runtime evidence surface must name the resolved delivery weapon so a
-- modified cast shape is observable without guessing.
do
  setTraits()
  M.dispatch("set_feature", { feature = "instantCastCooldown", value = true })
  local base = castRuntime()
  eq(#base.effectiveWeapons, 1, "base delivery weapon count")
  eq(base.effectiveWeapons[1], "WeaponCast", "base delivery weapon")
  check(base.weaponGateVerified, "base gate not verified")

  setTraits(modifier("CastProjectileBoon", "WeaponCastProjectile"))
  M.dispatch("status", {})
  local thrown = castRuntime()
  eq(#thrown.effectiveWeapons, 2, "thrown delivery weapon count")
  eq(thrown.effectiveWeapons[2], "WeaponCastProjectile", "thrown delivery weapon")
  check(thrown.weaponGateVerified, "thrown cast gate not verified")

  M.dispatch("set_feature", { feature = "instantCastCooldown", value = false })
end

print("hades2_cast_recast_variants_runtime_ok")
'''

with tempfile.TemporaryDirectory(prefix="mgt-cast-recast-runtime-") as td:
    td = Path(td)
    harness = td / "cast_recast_runtime.lua"
    harness.write_text(textwrap.dedent(HARNESS), encoding="utf-8")

    proc = subprocess.run(
        [LUA, str(harness), str(RUNTIME)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=30,
    )
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr)
        raise SystemExit(proc.returncode)
    assert "hades2_cast_recast_variants_runtime_ok" in proc.stdout, proc.stdout
    print(proc.stdout.strip())
