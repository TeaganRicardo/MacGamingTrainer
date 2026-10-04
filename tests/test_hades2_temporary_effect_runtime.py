from pathlib import Path
import subprocess
import tempfile
import textwrap

from lua_runtime_support import RESIDENT_DISPATCH_CONTRACT, require_lua52

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "Backend/games/hades2/runtime/hades.lua"
LUA = require_lua52("Well/temporary owner lifecycle runtime tests")

HARNESS = r'''
local runtimePath = assert(arg[1], "runtime path required")
local contractPath = assert(arg[2], "dispatch contract path required")

SessionState = {}
SessionMapState = {}
GameState = { Resources = {}, LifetimeResourcesGained = {}, RunHistory = {} }
ResourceData = {}
ResourceDisplayOrderData = {}
TraitElementData = {}
LootData = {}
ConsumableData = {}
RewardStoreData = {}
ScreenData = {}
MapState = { RoomRequiredObjects = {} }
LootObjects = {}
EnemyData = {}
PresetEventArgs = {}
UnitSetData = {}
UpdateTimers = function() end
FrameState = {}

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
  },
  CurrentRoom = { Name = "A_TestRoom" },
  NumRerolls = 0,
  SpellCharge = 0,
  PickedTraits = {},
}

local function deepCopy(value)
  if type(value) ~= "table" then return value end
  local result = {}
  for key, item in pairs(value) do result[key] = deepCopy(item) end
  return result
end
DeepCopyTable = deepCopy
ShallowCopyTable = function(value)
  local result = {}
  for key, item in pairs(value or {}) do result[key] = item end
  return result
end

TraitData = {
  TemporaryImprovedDefenseTrait = {
    Name = "TemporaryImprovedDefenseTrait",
    InheritFrom = { "ShopTrait" },
    RemainingUses = 5,
    UsesAsEncounters = true,
  },
  TemporaryHealExpirationTrait = {
    Name = "TemporaryHealExpirationTrait",
    InheritFrom = { "ShopTrait" },
    RemainingUses = 4,
    UsesAsEncounters = true,
    OnExpire = {
      FunctionName = "MockExpiryHeal",
      HealFraction = 0.5,
    },
  },
  BossMetaUpgradeKeepsake = {
    Name = "BossMetaUpgradeKeepsake",
    InheritFrom = { "GiftTrait" },
    Slot = "Keepsake",
    RemainingUses = 1,
  },
  LimitedSwapBonusTrait = {
    Name = "LimitedSwapBonusTrait",
    InheritFrom = { "ShopTrait" },
    Uses = 1,
    ForceSwaps = true,
    BlockStacking = true,
  },
  ManaOverTimeRefundTrait = {
    Name = "ManaOverTimeRefundTrait",
    InheritFrom = { "ShopTrait" },
    TotalManaRecovered = 500,
  },
}

local calls = {
  remove = 0,
  expiry = 0,
  updateNumber = 0,
  updateText = 0,
}
local nextId = 300
local failRemoveAfterMutation = false

local function rebuildDictionary()
  CurrentRun.Hero.TraitDictionary = {}
  for _, trait in ipairs(CurrentRun.Hero.Traits) do
    if trait.Name then
      CurrentRun.Hero.TraitDictionary[trait.Name] =
        CurrentRun.Hero.TraitDictionary[trait.Name] or {}
      table.insert(CurrentRun.Hero.TraitDictionary[trait.Name], trait)
    end
  end
end

HeroHasTrait = function(name)
  local values = CurrentRun.Hero.TraitDictionary[name]
  return type(values) == "table" and #values > 0
end

GetHeroTrait = function(name)
  local values = CurrentRun.Hero.TraitDictionary[name]
  return type(values) == "table" and values[1] or nil
end

AddTraitToHero = function(args)
  local source = args.TraitData or TraitData[args.TraitName]
  local trait = deepCopy(assert(source))
  trait.Name = trait.Name or args.TraitName
  trait.StackNum = trait.StackNum or 1
  nextId = nextId + 1
  trait.Id = nextId
  table.insert(CurrentRun.Hero.Traits, trait)
  rebuildDictionary()
  return trait
end

RemoveTraitData = function(hero, target, args)
  args = args or {}
  calls.remove = calls.remove + 1
  for index, trait in ipairs(hero.Traits) do
    if trait == target then
      table.remove(hero.Traits, index)
      break
    end
  end
  rebuildDictionary()
  if target.OnExpire and not args.SkipExpire then
    calls.expiry = calls.expiry + 1
  end
  if failRemoveAfterMutation then
    failRemoveAfterMutation = false
    error("synthetic temporary removal acknowledgement failure")
  end
end

UpdateTraitNumber = function()
  calls.updateNumber = calls.updateNumber + 1
end

TraitUIUpdateText = function()
  calls.updateText = calls.updateText + 1
end

IsGodTrait = function() return false end
GetAllUpgradeableGodTraits = function() return {} end
GetLootSourceName = function() return "" end

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
    fail("wrong error; expected '" .. needle .. "', got '" .. tostring(message) .. "'")
  end
end

local function status()
  return M.dispatch("status", { includeCatalogs = false })
end

local function findRow(name)
  for _, row in ipairs(status().currentRunTraits or {}) do
    if row.name == name then return row end
  end
  return nil
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
    expectedRemainingUses = row.remainingUses,
    includeCatalogs = false,
  }
end

local duration = AddTraitToHero({ TraitName = "TemporaryImprovedDefenseTrait" })
local row = assert(findRow(duration.Name), "temporary row missing")
eq(row.family, "temporary", "temporary family")
eq(row.remainingUses, 5, "remaining uses projection")
check(row.canSetRemainingUses == true, "temporary duration edit capability missing")
check(row.canExpire == true, "temporary expiry capability missing")
eq(row.levelCapability, "none", "temporary effect fabricated level editing")
eq(row.rarityCapability, "none", "temporary effect fabricated rarity editing")
eq(row.removalCapability, "singleInstanceForce", "temporary cancellation capability")
check(row.deferredIssue == nil, "temporary lifecycle remained deferred")

-- RemainingUses is not itself proof of Well/temporary ownership. Keepsakes and
-- other progression-owned runtime effects also use that counter and stay out of
-- #320 until their owner-specific #240 strategy is implemented.
local keepsake = AddTraitToHero({ TraitName = "BossMetaUpgradeKeepsake" })
local keepsakeRow = assert(findRow(keepsake.Name), "progression-owned keepsake row missing")
check(keepsakeRow.family ~= "temporary", "RemainingUses misclassified a keepsake as a Well effect")
check(keepsakeRow.canSetRemainingUses ~= true, "keepsake exposed Well duration editing")
check(keepsakeRow.canExpire ~= true, "keepsake exposed Well expiry semantics")
RemoveTraitData(CurrentRun.Hero, keepsake, { SkipExpire = true })

-- One real Well effect uses Uses rather than RemainingUses. It shares the
-- user-facing remaining-count editor, but native exhaustion leaves the trait
-- mounted/inactive instead of calling RemoveTraitData.
local limited = AddTraitToHero({ TraitName = "LimitedSwapBonusTrait" })
local limitedRow = assert(findRow(limited.Name), "Uses-backed Well row missing")
eq(limitedRow.family, "temporary", "Uses-backed Well owner family")
eq(limitedRow.remainingUses, 1, "Uses-backed Well count projection")
check(limitedRow.canSetRemainingUses == true, "Uses-backed Well count edit unavailable")
check(limitedRow.canExpire == true, "Uses-backed Well expiry unavailable")

local limitedSet = paramsFrom(limitedRow, "temporary-uses-set")
limitedSet.targetRemainingUses = 3
M.dispatch("set_trait_remaining_uses", limitedSet)
eq(limited.Uses, 3, "Uses-backed Well edit did not update native counter")
check(HeroHasTrait(limited.Name), "Uses-backed Well edit removed owner trait")

limitedRow = assert(findRow(limited.Name), "Uses-backed Well row missing after edit")
local beforeUsesExpireRemove = calls.remove
local beforeUsesExpireSideEffect = calls.expiry
local usesExpireParams = paramsFrom(limitedRow, "temporary-uses-expire")
M.dispatch("expire_trait", usesExpireParams)
eq(limited.Uses, 0, "Uses-backed Well expiry did not reach terminal counter")
check(not HeroHasTrait(limited.Name), "Uses-backed Well expiry did not perform native terminal teardown")
eq(calls.remove, beforeUsesExpireRemove + 1, "Uses-backed Well expiry did not call RemoveTraitData once")
eq(calls.expiry, beforeUsesExpireSideEffect, "Uses-backed Well expiry fabricated OnExpire")

local removeAfterUsesExpire = calls.remove
local duplicateUsesExpire = M.dispatch("expire_trait", usesExpireParams)
check(duplicateUsesExpire.duplicate == true, "Uses-backed Well expiry replay was not deduplicated")
eq(calls.remove, removeAfterUsesExpire, "Uses-backed Well expiry replayed teardown")

-- A Well owner without a duration counter is still a Well-managed effect. It
-- exposes cancellation only; duration/expiry controls must not be fabricated.
local passiveWell = AddTraitToHero({ TraitName = "ManaOverTimeRefundTrait" })
local passiveRow = assert(findRow(passiveWell.Name), "counterless Well row missing")
eq(passiveRow.family, "temporary", "counterless ShopTrait owner family")
check(passiveRow.remainingUses == nil, "counterless Well fabricated a remaining-use value")
check(passiveRow.canSetRemainingUses ~= true, "counterless Well fabricated duration editing")
check(passiveRow.canExpire ~= true, "counterless Well fabricated expiry")
eq(passiveRow.removalCapability, "singleInstanceForce", "counterless Well cancellation unavailable")
M.dispatch("remove_trait", paramsFrom(passiveRow, "temporary-counterless-cancel"))
check(not HeroHasTrait(passiveWell.Name), "counterless Well cancellation left owner mounted")

local staleDurationRow = row
local setParams = paramsFrom(row, "temporary-set-uses")
setParams.targetRemainingUses = 8
local setResult = M.dispatch("set_trait_remaining_uses", setParams)
eq(duration.RemainingUses, 8, "duration edit did not update owner counter")
check(calls.updateNumber > 0, "duration edit did not refresh native trait number")
check(calls.updateText > 0, "duration edit did not refresh native trait text")
eq(setResult.actionOutcome, "completed", "duration edit outcome")

local updatesAfterFirst = calls.updateNumber
local duplicateSet = M.dispatch("set_trait_remaining_uses", setParams)
check(duplicateSet.duplicate == true, "duration edit replay was not deduplicated")
eq(calls.updateNumber, updatesAfterFirst, "duration edit replayed native refresh")

expectError("Trait target changed since selection", function()
  local staleParams = paramsFrom(staleDurationRow, "temporary-stale-duration")
  staleParams.targetRemainingUses = 9
  M.dispatch("set_trait_remaining_uses", staleParams)
end)

-- Room transitions do not erase the mounted owner; a freshly observed row can
-- still edit its remaining duration after the room object changes.
CurrentRun.CurrentRoom = { Name = "B_TestRoom" }
row = assert(findRow(duration.Name), "temporary effect vanished across room transition")
local roomParams = paramsFrom(row, "temporary-room-transition")
roomParams.targetRemainingUses = 6
M.dispatch("set_trait_remaining_uses", roomParams)
eq(duration.RemainingUses, 6, "duration edit failed after room transition")

-- Cancellation is explicit teardown. It must never run natural OnExpire.
local heal = AddTraitToHero({ TraitName = "TemporaryHealExpirationTrait" })
local healRow = assert(findRow(heal.Name), "expiring temporary row missing")
local beforeCancelExpiry = calls.expiry
M.dispatch("remove_trait", paramsFrom(healRow, "temporary-cancel"))
check(not HeroHasTrait(heal.Name), "temporary cancellation left effect mounted")
eq(calls.expiry, beforeCancelExpiry, "temporary cancellation triggered OnExpire")

-- Expire Now is the opposite semantic: RemainingUses reaches zero and native
-- RemoveTraitData runs without SkipExpire, so OnExpire fires exactly once.
heal = AddTraitToHero({ TraitName = "TemporaryHealExpirationTrait" })
healRow = assert(findRow(heal.Name), "second expiring temporary row missing")
local expireParams = paramsFrom(healRow, "temporary-expire-now")
local beforeExpire = calls.expiry
local expireResult = M.dispatch("expire_trait", expireParams)
check(not HeroHasTrait(heal.Name), "Expire Now left effect mounted")
eq(heal.RemainingUses, 0, "Expire Now did not set natural terminal counter")
eq(calls.expiry, beforeExpire + 1, "Expire Now did not trigger OnExpire exactly once")
eq(expireResult.actionOutcome, "completed", "Expire Now outcome")

local removeAfterExpire = calls.remove
local duplicateExpire = M.dispatch("expire_trait", expireParams)
check(duplicateExpire.duplicate == true, "Expire Now replay was not deduplicated")
eq(calls.remove, removeAfterExpire, "Expire Now replayed teardown")
eq(calls.expiry, beforeExpire + 1, "Expire Now replay double-granted OnExpire")

-- A post-mutation acknowledgement failure is outcome-unknown. The owner state
-- remains coherent and the request can never run a second OnExpire.
heal = AddTraitToHero({ TraitName = "TemporaryHealExpirationTrait" })
healRow = assert(findRow(heal.Name), "outcome-unknown fixture row missing")
local unknownParams = paramsFrom(healRow, "temporary-expire-unknown")
local beforeUnknownExpiry = calls.expiry
failRemoveAfterMutation = true
expectError("MGT_OUTCOME_UNKNOWN", function()
  M.dispatch("expire_trait", unknownParams)
end)
check(not HeroHasTrait(heal.Name), "outcome-unknown expiry left effect mounted after mutation")
eq(calls.expiry, beforeUnknownExpiry + 1, "outcome-unknown expiry did not execute OnExpire once")
local beforeUnknownReplay = calls.remove
expectError("Previous action outcome is unknown; do not retry", function()
  M.dispatch("expire_trait", unknownParams)
end)
eq(calls.remove, beforeUnknownReplay, "outcome-unknown expiry replayed teardown")
eq(calls.expiry, beforeUnknownExpiry + 1, "outcome-unknown replay double-granted OnExpire")

-- disable_all is not an undo path for game-owned temporary effects.
duration = AddTraitToHero({ TraitName = "TemporaryImprovedDefenseTrait" })
M.dispatch("disable_all", { includeCatalogs = false })
check(HeroHasTrait(duration.Name), "disable_all removed a game-owned temporary effect")

print("hades2_temporary_effect_runtime_ok")
'''

with tempfile.TemporaryDirectory(prefix="mgt-temporary-effect-") as td:
    td = Path(td)
    harness = td / "temporary_effect_runtime.lua"
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
    assert "hades2_temporary_effect_runtime_ok" in proc.stdout, proc.stdout
    print(proc.stdout.strip())
