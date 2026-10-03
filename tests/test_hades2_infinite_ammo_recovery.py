"""Resident regression for pickup-compatible infinite ammo on Argent Skull.

Hades II 1.143476 / Steam 25481925 gives WeaponLob a native recoverable
ammo lifecycle:

* OnWeaponFired returns immediately when HasHeroTraitValue("UnlimitedAmmo") is
  true.
* Otherwise it records LobAmmoInFlight and spends ammo.
* Projectile death consumes that in-flight count and creates LobAmmoPack.
* LobAmmoPack pickup calls AddAmmo, which also fires OnCollectAmmo callbacks.

The Trainer must therefore provide unlimited firing without impersonating the
native UnlimitedAmmo trait value. Doing so suppresses the game's own in-flight
bookkeeping and makes the fired skull unrecoverable.

This harness models that target-build seam while exercising the real resident
feature installation and hook ownership.
"""

import subprocess
import tempfile
import textwrap
from pathlib import Path

from lua_runtime_support import require_lua52

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "Backend/games/hades2/runtime/hades.lua"
LUA = require_lua52("infinite ammo recovery runtime behavior tests")

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
MapState = { RoomRequiredObjects = {}, EquippedWeapons = { WeaponLob = true } }
LootObjects = {}
ConsumableData = {}
RewardStoreData = {}
UpdateTimers = function() end
CodexOrdering = { OlympianGods = {}, Order = {} }
TraitData = {}
LootData = {}
UnitSetData = {}

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
    Ammo = { WeaponLob = 4 },
  },
  CurrentRoom = {},
  NumRerolls = 0,
  SpellCharge = 0,
  PickedTraits = {},
  BannedTraits = {},
}

local MAX_AMMO = 4
local packs = 0
local collectEffects = 0
local nativeUnlimitedAmmo = false

local function fail(message) error("ASSERTION FAILED: " .. message, 0) end
local function check(value, message) if not value then fail(message) end end
local function eq(actual, expected, message)
  if actual ~= expected then
    fail(message .. ": expected=" .. tostring(expected) .. " actual=" .. tostring(actual))
  end
end

local function incrementTableValue(owner, key, amount)
  owner[key] = (owner[key] or 0) + (amount or 1)
end
local function decrementTableValue(owner, key, amount)
  owner[key] = (owner[key] or 0) - (amount or 1)
end

HasHeroTraitValue = function(valueName)
  if valueName == "UnlimitedAmmo" then return nativeUnlimitedAmmo end
  return false
end
GetMaxAmmo = function(weaponName)
  if weaponName == "WeaponLob" then return MAX_AMMO end
  return 0
end
UpdateWeaponAmmo = function(weaponName, delta, _)
  local current = CurrentRun.Hero.Ammo[weaponName] or 0
  local nextValue = current + delta
  if nextValue > GetMaxAmmo(weaponName) then nextValue = GetMaxAmmo(weaponName) end
  CurrentRun.Hero.Ammo[weaponName] = nextValue
end

local function getCurrentAmmo(weaponName)
  return CurrentRun.Hero.Ammo[weaponName] or 0
end
local function spendAmmo(weaponName)
  UpdateWeaponAmmo(weaponName, -1)
end
local function addAmmo(weaponName)
  UpdateWeaponAmmo(weaponName, 1)
  collectEffects = collectEffects + 1
end

-- Target-build WeaponLob OnWeaponFired semantics, reduced to the exact seam
-- that the Trainer hooks.
local function nativeFire(numProjectiles)
  if HasHeroTraitValue("UnlimitedAmmo") then
    return false
  end
  numProjectiles = numProjectiles or 1
  SessionMapState.AmmoAtFireStart = getCurrentAmmo("WeaponLob")
  if numProjectiles > 1 then
    UpdateWeaponAmmo("WeaponLob", -numProjectiles)
    incrementTableValue(SessionMapState, "LobAmmoInFlight", numProjectiles)
  else
    incrementTableValue(SessionMapState, "LobAmmoInFlight")
    spendAmmo("WeaponLob")
  end
  return true
end

-- Target-build WeaponLobAmmoDrop begins by requiring LobAmmoInFlight > 0 and
-- consumes one unit when it materializes a LobAmmoPack.
local function nativeProjectileDeath()
  if not SessionMapState.LobAmmoInFlight or SessionMapState.LobAmmoInFlight <= 0 then
    return false
  end
  decrementTableValue(SessionMapState, "LobAmmoInFlight")
  packs = packs + 1
  return true
end

local function nativeCollectPack()
  if packs <= 0 then return false end
  packs = packs - 1
  addAmmo("WeaponLob")
  return true
end

dofile(runtimePath)
local M = assert(__MacGamingTrainerV1, "resident runtime did not initialize")

M.dispatch("set_feature", { feature = "infiniteAmmo", value = true })

-- RED on the current implementation: spoofing UnlimitedAmmo makes the real
-- target-build OnWeaponFired return before it records recoverable ammo.
eq(HasHeroTraitValue("UnlimitedAmmo"), false,
  "Trainer must not impersonate the native UnlimitedAmmo trait value")

-- The current target also has a real LobGunAspect whose own trait data sets
-- UnlimitedAmmo=true and removes the ammo-drop lifecycle. The Trainer must
-- preserve that native aspect signal rather than forcing either value.
nativeUnlimitedAmmo = true
eq(HasHeroTraitValue("UnlimitedAmmo"), true,
  "Trainer masked the native UnlimitedAmmo aspect value")
check(not nativeFire(), "native UnlimitedAmmo aspect unexpectedly entered the recovery lifecycle")
nativeUnlimitedAmmo = false

for i = 1, 6 do
  check(nativeFire(), "native WeaponLob fire path was bypassed at shot " .. tostring(i))
  eq(getCurrentAmmo("WeaponLob"), MAX_AMMO,
    "infinite supply did not preserve uninterrupted firing at shot " .. tostring(i))
  check(nativeProjectileDeath(), "fired skull did not enter recoverable lifecycle")
end

eq(packs, 6, "projectile deaths did not create one native recovery pack per fired skull")
eq(SessionMapState.LobAmmoInFlight, 0, "in-flight recovery bookkeeping did not drain")

-- Spread Shot spends and records NumProjectiles as one native volley. Infinite
-- supply must not collapse that accounting to a single recovery object.
check(nativeFire(3), "spread-shot native fire path was bypassed")
eq(getCurrentAmmo("WeaponLob"), MAX_AMMO, "spread-shot infinite supply reduced carried ammo")
eq(SessionMapState.LobAmmoInFlight, 3, "spread-shot in-flight count was not preserved")
for _ = 1, 3 do
  check(nativeProjectileDeath(), "spread-shot projectile did not produce a recovery pack")
end
eq(packs, 9, "spread-shot recovery pack count drifted")
eq(SessionMapState.LobAmmoInFlight, 0, "spread-shot in-flight bookkeeping did not drain")

check(nativeCollectPack(), "native ammo pack could not be collected")
eq(getCurrentAmmo("WeaponLob"), MAX_AMMO, "pickup inflated or reduced carried ammo")
eq(collectEffects, 1, "pickup-owned effect seam did not fire exactly once")

M.dispatch("set_feature", { feature = "infiniteAmmo", value = false })
eq(HasHeroTraitValue("UnlimitedAmmo"), false, "disable leaked native UnlimitedAmmo semantics")
spendAmmo("WeaponLob")
eq(getCurrentAmmo("WeaponLob"), MAX_AMMO - 1, "disable did not restore native ammo spending")

print("hades2_infinite_ammo_recovery_runtime_ok")
'''

with tempfile.TemporaryDirectory(prefix="mgt-infinite-ammo-recovery-") as td:
    td = Path(td)
    harness = td / "infinite_ammo_recovery.lua"
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

    if "hades2_infinite_ammo_recovery_runtime_ok" not in proc.stdout:
        print(proc.stdout)
        raise SystemExit("missing infinite-ammo recovery success marker")

print("hades2_infinite_ammo_recovery_ok")
