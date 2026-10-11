"""Target-build damage/effect/force/time models cross the real resident JSON seam."""
import subprocess
import tempfile
from pathlib import Path
from lua_runtime_support import RESIDENT_DISPATCH_CONTRACT, require_lua52

ROOT = Path(__file__).resolve().parents[1]
LUA = require_lua52("Invincibility hostile-effect behavior")
HARNESS = r'''
SessionState = { GameplaySlows = {}, PlayerGameplaySlows = {} }; SessionMapState = {}
GameState = { Resources = {}, LifetimeResourcesGained = {}, RunHistory = {} }
ResourceData = {}; ResourceDisplayOrderData = {}; TraitElementData = {}
EnemyData = {}; TraitData = {}; LootData = {}; ConsumableData = {}; RewardStoreData = {}
MapState = { RoomRequiredObjects = {} }; LootObjects = {}; ScreenData = {}
CodexOrdering = { OlympianGods = {}, Order = {} }
UpdateTimers = function() end
local function hero(id)
  return { ObjectId = id, Health = 100, MaxHealth = 100, Mana = 50, MaxMana = 50,
    HealthBuffer = 20, Hits = 3, Traits = {}, TraitDictionary = {}, Elements = {},
    BoonData = {}, InvulnerableFlags = {}, ImmuneToForceFlags = {} }
end
CurrentRun = { Hero = hero(1), CurrentRoom = {}, NumRerolls = 0, PickedTraits = {}, BannedTraits = {} }
local units = { [1] = CurrentRun.Hero }
local blocks, effects, forceImmune, playerTime = {}, {}, {}, {}
local unitTokens = { [1] = {} }
local function count(id, name) return blocks[id] and blocks[id][name] and 1 or 0 end
AddEffectBlock = function(args)
  blocks[args.Id] = blocks[args.Id] or {}
  blocks[args.Id][args.Name] = true
  return args
end
RemoveEffectBlock = function(args)
  if args.All ~= true and not (type(args.All) == 'string' and string.lower(args.All) == 'true')
      and args.Name and blocks[args.Id] then blocks[args.Id][args.Name] = nil end
  return args
end
__MGTHadesNativeV1 = {
  abi = 1,
  unitIdentity = function(id) return unitTokens[id] end,
  snapshotEffectBlocks = function(id)
    if not unitTokens[id] then return nil, 'unit unavailable' end
    local snapshot = { objectId = id, unitToken = unitTokens[id], blocked = {} }
    for name, blocked in pairs(blocks[id] or {}) do snapshot.blocked[name] = blocked end
    return snapshot
  end,
}
SetupHeroObject = function()
  local unit = CurrentRun.Hero
  units[unit.ObjectId] = unit; unitTokens[unit.ObjectId] = {}
  blocks[unit.ObjectId] = {}; forceImmune[unit.ObjectId] = false
  unit.InvulnerableFlags = {}; unit.ImmuneToForceFlags = {}
end
ClearEffect = function(args)
  if effects[args.Id] then effects[args.Id][args.Name] = nil end
end
ApplyEffect = function(args)
  local unit = units[args.DestinationId]
  if count(unit.ObjectId, args.EffectName) > 0 then return end
  if not args.CanAffectInvulnerable and next(unit.InvulnerableFlags) then return end
  effects[unit.ObjectId] = effects[unit.ObjectId] or {}
  effects[unit.ObjectId][args.EffectName] = true
  if args.EffectName == 'EliteManaDrain' then unit.Mana = unit.Mana - 10 end
end
SetUnitInvulnerable = function(unit, flag) unit.InvulnerableFlags[flag] = true end
SetUnitVulnerable = function(unit, flag) unit.InvulnerableFlags[flag] = nil end
SetThingProperty = function(args)
  local id = args.DestinationId or CurrentRun.Hero.ObjectId
  if args.Property == 'ImmuneToForce' then forceImmune[id] = args.Value end
  if args.Property == 'ElapsedTimeMultiplier' then playerTime[id] = args.Value end
end
AddPlayerImmuneToForce = function(flag)
  CurrentRun.Hero.ImmuneToForceFlags[flag] = true
  forceImmune[CurrentRun.Hero.ObjectId] = true
end
RemovePlayerImmuneToForce = function(flag)
  CurrentRun.Hero.ImmuneToForceFlags[flag] = nil
  forceImmune[CurrentRun.Hero.ObjectId] = next(CurrentRun.Hero.ImmuneToForceFlags) ~= nil
end
Damage = function(unit, args)
  unit.Health = unit.Health - args.DamageAmount
  unit.HealthBuffer = math.max(0, unit.HealthBuffer - args.DamageAmount)
end
GetPlayerGameplayElapsedTimeMultiplier = function()
  local result = 1
  for _, value in pairs(SessionState.PlayerGameplaySlows) do result = math.min(result, value.Amount) end
  return result
end
GameplaySetElapsedTimeMultiplier = function(args)
  local value
  if not args.Reverse then value = { Amount = args.ElapsedTimeMultiplier } end
  SessionState.GameplaySlows[args.Name] = value
  if args.ApplyToPlayerUnits then
    SessionState.PlayerGameplaySlows[args.Name] = value
    playerTime[CurrentRun.Hero.ObjectId] = GetPlayerGameplayElapsedTimeMultiplier()
  end
end
-- Engine effects/force precede Lua Damage, including zero-damage attacks.
local function projectile(name, effectNames, force, canAffectInvulnerable, damage)
  local unit = CurrentRun.Hero
  for _, effectName in ipairs(effectNames) do
    ApplyEffect({ DestinationId = unit.ObjectId, EffectName = effectName,
      CanAffectInvulnerable = canAffectInvulnerable })
  end
  if force and not forceImmune[unit.ObjectId] then unit.Displaced = true end
  unit.Hits = unit.Hits + 1
  Damage(unit, { DamageAmount = damage or 8, SourceProjectile = name, AttackerId = 10 })
end
dofile(assert(arg[1])); dofile(assert(arg[2]))
local M = __MacGamingTrainerV1
local function enable(value)
  return M.dispatch('set_feature', { feature = 'invincibility', value = value, includeCatalogs = false })
end
'''
CASES = {
    "stasis": r'''
enable(true)
for _, name in ipairs({ 'EliteStasisDeath', 'TimeTrapStasis', 'TimeElementalStasis',
  'ChronosMiniRiftStasis', 'ChronosDashStasis', 'ChronosStasisExtended' }) do
  projectile(name, { 'StasisStun' }, false, true)
  assert(not (effects[1] and effects[1].StasisStun), name .. ' froze the protected Hero')
end
''',
    "drain": r'''
enable(true)
projectile('EliteManaDrain', { 'EliteManaDrain', 'KnockbackGrip' }, false, true)
assert(CurrentRun.Hero.Mana == 50, 'Drainer bypassed the Lua damage owner')
assert(not (effects[1] and effects[1].KnockbackGrip), 'zero-damage drain halted the Hero')
''',
    "force": r'''
enable(true)
for _, name in ipairs({ 'EliteVacuum', 'ChronosGrindVacuum', 'ChronosRushKnockback' }) do
  projectile(name, { 'KnockbackGrip' }, true, true)
  assert(not CurrentRun.Hero.Displaced, name .. ' displaced the protected Hero')
  assert(not (effects[1] and effects[1].KnockbackGrip), name .. ' halted the protected Hero')
end
''',
    "fangs": r'''
enable(true)
-- Each selectable attribute retains enemy-owned behavior. Only player payloads
-- cross Invincibility's owners. Scraper's damage/stun already obey invulnerability.
local attributes = {
  Blink = {}, ExtraDamage = { 'EliteAttributeStun' }, Fog = {}, Frenzy = {},
  HeavyArmor = {}, ManaDrain = { 'EliteManaDrain', 'KnockbackGrip' }, Massive = {},
  Miasma = { 'MiasmaSlow' }, Molten = { 'LavaSlow' }, Orbit = { 'HeroOnHitStun' },
  Rooting = { 'Rooted', 'MeleeAttackVictimGrip' }, SpreadHitShields = {},
  StasisDeath = { 'StasisStun' }, Unflinching = {}, Vacuuming = {},
  Hex = { 'HecatePolymorphStun' }, Rifts = { 'HeroOnHitStun' }, Homing = {}, Metallic = {}, Radial = {},
}
for name, payload in pairs(attributes) do
  local enemy = hero(10); units[10] = enemy
  ApplyEffect({ DestinationId = 10, EffectName = 'EnemyEnhancement', CanAffectInvulnerable = true })
  Damage(enemy, { DamageAmount = 7, AttackerId = 1 })
  assert(effects[10].EnemyEnhancement and enemy.Health == 93, name .. ' changed the enemy owner')
  projectile(name, payload, name == 'Vacuuming', false)
  assert(CurrentRun.Hero.Health == 100 and CurrentRun.Hero.HealthBuffer == 20
    and CurrentRun.Hero.Hits == 3 and not CurrentRun.Hero.Displaced, name .. ' harmed the Hero')
  for _, effect in ipairs(payload) do
    assert(not (effects[1] and effects[1][effect]), name .. ' applied ' .. effect)
  end
end
''',
    "radial": r'''
-- SiegeVine and ZombieSpawner can select Radial in the supported content.
-- EliteRadialBeams owns its native enemy weapon and 11-point player hit.
local enemy = hero(10); units[10] = enemy
enemy.Weapons = { EliteRadialBeams = true }
enable(true)
projectile('EliteRadialBeams', {}, false, false, 11)
assert(CurrentRun.Hero.Health == 100 and CurrentRun.Hero.HealthBuffer == 20 and CurrentRun.Hero.Hits == 3,
  'Radial damaged protected Hero health/armor/hit accounting')
assert(enemy.Weapons.EliteRadialBeams, 'Radial enemy weapon was removed')
Damage(enemy, { DamageAmount = 11, AttackerId = 1 })
assert(enemy.Health == 89, 'Radial enemy damage owner was changed')
enable(false)
projectile('EliteRadialBeams', {}, false, false, 11)
assert(CurrentRun.Hero.Health == 89 and CurrentRun.Hero.HealthBuffer == 9 and CurrentRun.Hero.Hits == 4,
  'disable retained Radial protection')
''',
    "existing_effects": r'''
effects[1] = { StasisStun = true, Rooted = true, MiasmaSlow = true,
  WebSlow = true, ScreamerSlow = true, HeroOnHitStun = true, KnockbackGrip = true,
  SpeedBoost = true, ChaosStun = true, ChronosPolymorphStun = true }
enable(true)
for _, name in ipairs({ 'StasisStun', 'Rooted', 'MiasmaSlow', 'WebSlow',
  'ScreamerSlow', 'HeroOnHitStun', 'KnockbackGrip' }) do
  assert(not effects[1][name], 'enabling retained ' .. name)
end
assert(effects[1].SpeedBoost and effects[1].ChaosStun and effects[1].ChronosPolymorphStun,
  'enabling changed a player skill/curse or a scripted encounter transition')
ApplyEffect({ DestinationId = 1, EffectName = 'SpeedBoost', CanAffectInvulnerable = true })
assert(effects[1].SpeedBoost, 'player buff was suppressed')
''',
    "time": r'''
GameplaySetElapsedTimeMultiplier({ Name = 'ChronosTimeSlow', ElapsedTimeMultiplier = 0.3,
  ApplyToPlayerUnits = true })
assert(playerTime[1] == 0.3)
enable(true)
assert(playerTime[1] == 1, 'enabling retained an active Chronos player slow')
assert(SessionState.GameplaySlows.ChronosTimeSlow.Amount == 0.3, 'changed enemy/encounter time')
GameplaySetElapsedTimeMultiplier({ Name = 'PlayerSpell', ElapsedTimeMultiplier = 0.1,
  ApplyToPlayerUnits = true })
assert(playerTime[1] == 0.1, 'player-owned time effect was suppressed')
GameplaySetElapsedTimeMultiplier({ Name = 'PlayerSpell', Reverse = true, ApplyToPlayerUnits = true })
GameplaySetElapsedTimeMultiplier({ Name = 'ChronosTimeSlow', ElapsedTimeMultiplier = 0.3,
  ApplyToPlayerUnits = true })
assert(playerTime[1] == 1, 'later Chronos slow reached the protected Hero')
enable(false)
assert(playerTime[1] == 0.3, 'disable lost the still-active native slow')
enable(true)
GameplaySetElapsedTimeMultiplier({ Name = 'ChronosTimeSlow', Reverse = true, ApplyToPlayerUnits = true })
enable(false)
assert(playerTime[1] == 1, 'disable resurrected a finished Chronos slow')
''',
    "lifecycle": r'''
AddEffectBlock({ Id = 1, Name = 'StasisStun' }); AddPlayerImmuneToForce('NativeSkill')
enable(true); enable(true)
assert(count(1, 'StasisStun') == 1, 'repeat enable changed native set membership')
enable(false)
assert(count(1, 'StasisStun') == 1 and forceImmune[1], 'disable removed native protection')
RemovePlayerImmuneToForce('NativeSkill'); RemoveEffectBlock({ Id = 1, Name = 'StasisStun' })
enable(true)
local old = CurrentRun.Hero
-- Native World disposal removes its units before the replacement world is
-- observed. Retained Lua Hero tables are not retained native Unit objects.
units[1] = nil; unitTokens[1] = nil; blocks[1] = nil; forceImmune[1] = nil
CurrentRun = { Hero = hero(2), CurrentRoom = {}, NumRerolls = 0, PickedTraits = {}, BannedTraits = {} }
units[2] = CurrentRun.Hero; unitTokens[2] = {}
local state = M.dispatch('status', { includeCatalogs = false })
assert(state.activeFeatures.invincibility, 'Hero replacement lost durable intent')
assert(count(1, 'StasisStun') == 0 and not next(old.ImmuneToForceFlags), 'old owner retained protection')
projectile('EliteStasisDeath', { 'StasisStun' }, true, true)
assert(not (effects[2] and effects[2].StasisStun) and not CurrentRun.Hero.Displaced)
CurrentRun.Hero.ImmuneToForceFlags = {}; forceImmune[2] = false
M.dispatch('status', { includeCatalogs = false })
assert(forceImmune[2], 'room reset lost protection on the same Hero')
M.dispatch('cleanup', {})
assert(count(2, 'StasisStun') == 0 and not forceImmune[2], 'cleanup retained Trainer protection')
projectile('EliteStasisDeath', { 'StasisStun' }, true, true)
assert(effects[2].StasisStun and CurrentRun.Hero.Displaced, 'cleanup changed native behavior')
''',
    "other_hostile_payloads": r'''
enable(true)
-- These payloads occur on hostile projectiles/terrain outside the Fangs list.
-- A protection on Hero must leave the same effect on an enemy untouched.
units[10] = hero(10)
for _, name in ipairs({ 'ChillEffect', 'ChillStatueEffect', 'MatiHypnosisSlow',
  'VacuumSlow', 'Inked', 'WebSlow', 'GhostWallHalt', 'ScreamerSlow', 'LavaSlow',
  'OnHitStun', 'HeroOnHitStun', 'EliteAttributeStun', 'Rooted', 'MeleeAttackVictimGrip' }) do
  ApplyEffect({ DestinationId = 1, EffectName = name, CanAffectInvulnerable = true })
  ApplyEffect({ DestinationId = 10, EffectName = name, CanAffectInvulnerable = true })
  assert(not (effects[1] and effects[1][name]) and effects[10][name], name .. ' lost target isolation')
end
''',
    "reused_hero_id": r'''
enable(true)
local old = CurrentRun.Hero
CurrentRun.Hero = hero(1); units[1] = CurrentRun.Hero; unitTokens[1] = {}
-- The engine has reset the unit and a native skill owns the new unit's block.
blocks[1] = {}; forceImmune[1] = false
AddEffectBlock({ Id = 1, Name = 'StasisStun' }); AddPlayerImmuneToForce('NativeSkill')
M.dispatch('status', { includeCatalogs = false })
assert(count(1, 'StasisStun') == 1, 'old owner removed a replacement native block')
assert(not next(old.ImmuneToForceFlags), 'old Hero retained the Trainer flag')
enable(false)
assert(count(1, 'StasisStun') == 1 and forceImmune[1], 'disable removed replacement native protection')
''',
    "hook_replacement": r'''
enable(true)
local replacement = function() return 0.7 end
GetPlayerGameplayElapsedTimeMultiplier = replacement
enable(false)
assert(GetPlayerGameplayElapsedTimeMultiplier == replacement, 'disable replaced a foreign time hook')
''',
    "native_set_intent": r'''
AddEffectBlock({ Id = 1, Name = 'StasisStun' })
enable(true)
RemoveEffectBlock({ Id = 1, Name = 'StasisStun' })
assert(count(1, 'StasisStun') == 1, 'native cleanup defeated Trainer protection')
AddEffectBlock({ Id = 1, Name = 'Inked' })
AddEffectBlock({ Id = 1, Name = 'Inked' })
RemoveEffectBlock({ Id = 1, Name = 'Inked' })
assert(count(1, 'Inked') == 1, 'delayed native remover defeated protection')
AddEffectBlock({ Id = 1, Name = 'Rooted' })
RemoveEffectBlock({ Id = 1, All = true })
enable(false)
assert(count(1, 'StasisStun') == 0 and count(1, 'Inked') == 0,
  'disable resurrected a finished native block')
assert(count(1, 'Rooted') == 1, 'disable erased a current native block')
''',
    "same_hero_rebinding": r'''
enable(true)
local oldFlags = CurrentRun.Hero.InvulnerableFlags
CurrentRun.CurrentRoom = {}
SetupHeroObject()
AddEffectBlock({ Id = 1, Name = 'StasisStun' })
AddPlayerImmuneToForce('NativeSkill')
M.dispatch('status', { includeCatalogs = false })
enable(false)
assert(count(1, 'StasisStun') == 1 and forceImmune[1], 'old owner erased replacement protection')
assert(not oldFlags.MacGamingTrainerInvincibility, 'old owner leaked its flag')
''',
    "sampling_events_and_flags": r'''
AddEffectBlock({ Id = 1, Name = 'StasisStun' })
local nativeSnapshot = __MGTHadesNativeV1.snapshotEffectBlocks
__MGTHadesNativeV1.snapshotEffectBlocks = function(id)
  local stale = nativeSnapshot(id)
  -- Native query table allocation can run same-thread game finalizers after
  -- the C collector read. These later native events supersede that snapshot.
  RemoveEffectBlock({ Id = id, Name = 'StasisStun' })
  AddEffectBlock({ Id = id, Name = 'Inked' })
  CurrentRun.Hero.InvulnerableFlags = { NativeSkill = true }
  CurrentRun.Hero.ImmuneToForceFlags = { NativeSkill = true }
  return stale
end
enable(true); enable(false)
assert(count(1, 'StasisStun') == 0 and count(1, 'Inked') == 1, 'sampling lost last native events')
assert(CurrentRun.Hero.InvulnerableFlags.NativeSkill and CurrentRun.Hero.ImmuneToForceFlags.NativeSkill,
  'sampling restored stale flag owners')
''',
    "sampling_failure": r'''
local add, remove, setup = AddEffectBlock, RemoveEffectBlock, SetupHeroObject
__MGTHadesNativeV1.snapshotEffectBlocks = function(id)
  AddEffectBlock({ Id = id, Name = 'Inked' })
  return nil, 'unreadable block set'
end
assert(not pcall(enable, true), 'unreadable snapshot was treated as empty')
assert(not M.terminalActionUnknown, 'read failure before Trainer writes closed trust')
assert(AddEffectBlock == add and RemoveEffectBlock == remove and SetupHeroObject == setup,
  'failed sampling retained temporary interception')
assert(count(1, 'Inked') == 1 and count(1, 'StasisStun') == 0,
  'failed sampling rewrote native membership')
assert(not next(CurrentRun.Hero.InvulnerableFlags) and not next(CurrentRun.Hero.ImmuneToForceFlags))
''',
    "native_returns_and_all": r'''
enable(true)
local add = { Id = 1, Name = 'Inked', All = true }
local all = { Id = 1, Name = 'Inked', All = 'TrUe' }
assert(AddEffectBlock(add) == add and RemoveEffectBlock(all) == all, 'native args-table result changed')
local remove = { Id = 1, Name = 'StasisStun', All = 1 }
assert(RemoveEffectBlock(remove) == remove, 'suppressed native remove lost its result')
enable(false)
assert(count(1, 'Inked') == 1 and count(1, 'StasisStun') == 0,
  'All was confused with named-set membership')
''',
    "world_change_during_native_write": r'''
local add = AddEffectBlock
AddEffectBlock = function(args)
  add(args)
  CurrentRun.CurrentRoom = {}
end
local ok, message = pcall(enable, true)
assert(not ok and tostring(message):find('MGT_OUTCOME_UNKNOWN:', 1, true),
  'native write followed a changed world and reported success')
assert(M.terminalActionUnknown)
assert(count(1, 'StasisStun') == 0, 'later Trainer writes crossed the changed owner')
''',
    "partial_install_unknown": r'''
SetUnitInvulnerable = function(unit, flag)
  unit.InvulnerableFlags[flag] = true
  error('after invulnerability mutation')
end
local ok, message = pcall(enable, true)
assert(not ok and tostring(message):find('MGT_OUTCOME_UNKNOWN:', 1, true),
  'partial installation did not surface uncertainty')
assert(M.terminalActionUnknown, 'partial installation retained mutation trust')
assert(next(CurrentRun.Hero.InvulnerableFlags), 'partial owner evidence was discarded')
local before = count(1, 'StasisStun')
assert(not pcall(enable, false), 'uncertain operation was automatically retried')
assert(count(1, 'StasisStun') == before, 'uncertain cleanup changed native membership')
local args = { Id = 1, Name = 'Inked' }
assert(AddEffectBlock(args) == args, 'Trainer taint stopped an ordinary game Add')
SetupHeroObject()
assert(not next(CurrentRun.Hero.InvulnerableFlags), 'Trainer taint stopped ordinary Hero setup')
local replacement = { Id = 1, Name = 'StasisStun' }
assert(AddEffectBlock(replacement) == replacement and RemoveEffectBlock(replacement) == replacement)
assert(count(1, 'StasisStun') == 0, 'uncertain old lease suppressed replacement Unit cleanup')
GameplaySetElapsedTimeMultiplier({ Name = 'ChronosTimeSlow', ElapsedTimeMultiplier = 0.3,
  ApplyToPlayerUnits = true })
assert(playerTime[1] == 0.3, 'uncertain old time lease changed replacement Unit gameplay')
''',
    "partial_release_unknown": r'''
enable(true)
local nativeProperty = SetThingProperty
SetThingProperty = function(args)
  nativeProperty(args)
  if args.Property == 'ImmuneToForce' and not args.Value then error('after force mutation') end
end
local ok, message = pcall(enable, false)
assert(not ok and tostring(message):find('MGT_OUTCOME_UNKNOWN:', 1, true),
  'partial release reported success')
assert(M.terminalActionUnknown, 'partial release retained mutation trust')
assert(not pcall(enable, false), 'partial release was blindly retried')
SetupHeroObject()
GameplaySetElapsedTimeMultiplier({ Name = 'ChronosTimeSlow', ElapsedTimeMultiplier = 0.3,
  ApplyToPlayerUnits = true })
assert(playerTime[1] == 0.3, 'uncertain old release changed the rebuilt Unit time owner')
''',
}
with tempfile.TemporaryDirectory(prefix="mgt-invincibility-") as temporary:
    harness = Path(temporary) / "invincibility.lua"
    failures = []
    for name, case in CASES.items():
        harness.write_text(HARNESS + case + "\nprint('invincibility_ok')\n")
        result = subprocess.run(
            [LUA, str(harness), str(ROOT / "Backend/games/hades2/runtime/hades.lua"),
             str(RESIDENT_DISPATCH_CONTRACT)], capture_output=True, text=True, timeout=15,
        )
        if result.returncode:
            failures.append(name + ": " + result.stderr)
        else:
            print(name + ": " + result.stdout.strip())
    assert not failures, "\n".join(failures)
