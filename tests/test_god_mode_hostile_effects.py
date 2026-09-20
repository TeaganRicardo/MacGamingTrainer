from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
lua = (ROOT / "Backend/games/hades2/runtime/hades.lua").read_text()

# Runtime changes in this slice must advance the resident revision.
assert 'version = 1, revision = 41' in lua
assert 'godModeHitBaseline' in lua
assert 'godModeHitBaselineKnown' in lua

assert 'local godModeBlockedEffects = {' in lua
deny = lua[lua.index('local godModeBlockedEffects = {'):lua.index('}', lua.index('local godModeBlockedEffects = {')) + 1]
for effect in ('HecatePolymorphStun', 'MiasmaSlow'):
    assert effect in deny, effect
for effect in ('ChronosPolymorphStun', 'ChaosStun', 'MedeaPoison', 'SheepSickSlow'):
    assert effect not in deny, effect

install = lua[lua.index('local function installGodMode()'):lua.index('local function installHealth()')]
for token in ('AddEffectBlock', 'RemoveEffectBlock', 'ClearEffect', 'godModeBlockedEffects'):
    assert token in install, token
assert 'for _, effectName in ipairs(godModeBlockedEffects)' in install
assert 'AddEffectBlock({ Id = hero.ObjectId, Name = effectName })' in install
assert 'ClearEffect({ Id = hero.ObjectId, Name = effectName })' in install

damage_router = lua[lua.index('local function ensureHeroDamageRouter()'):lua.index('local function installGodMode()')]
god_branch_start = damage_router.index('if M.godMode then')
god_branch = damage_router[god_branch_start:damage_router.index('end', god_branch_start) + len('end')]
assert 'restoreGodModeHitCount(victim)' in god_branch
assert god_branch.index('restoreGodModeHitCount(victim)') < god_branch.index('return nil')

assert 'M.godModeHitBaseline = hero.Hits' in install
assert 'M.godModeHitBaselineKnown = true' in install

release = lua[lua.index('local function releaseGodMode()'):lua.index('local function releaseHealth()')]
assert 'for _, effectName in ipairs(godModeBlockedEffects)' in release
assert 'RemoveEffectBlock' in release
assert 'M.godEffectBlockHero = nil' in release
assert 'restoreGodModeHitCount(M.godModeHitHero)' in release
assert 'M.godModeHitBaselineKnown = false' in release

enforce = lua[lua.index('local function enforceLocks()'):lua.index('M.enforceLocksInternal = enforceLocks')]
assert 'restoreGodModeHitCount(CurrentRun.Hero)' in enforce

# Engine-level effect blocks cover effects applied by projectiles/terrain without
# installing a broad global ApplyEffect hook that could suppress player buffs.
assert 'installHook("ApplyEffect"' not in lua

print("god_mode_hostile_effects_ok")
