from pathlib import Path

from runtime_revision_support import runtime_revision

ROOT = Path(__file__).resolve().parents[1]
lua = (ROOT / "Backend/games/hades2/runtime/hades.lua").read_text()

# Runtime changes in this slice must advance the resident revision.
assert runtime_revision(lua) >= 42
assert 'invincibilityHitBaseline' in lua
assert 'invincibilityHitBaselineKnown' in lua

assert 'local invincibilityBlockedEffects = {' in lua
deny = lua[lua.index('local invincibilityBlockedEffects = {'):lua.index('}', lua.index('local invincibilityBlockedEffects = {')) + 1]
for effect in ('HecatePolymorphStun', 'MiasmaSlow'):
    assert effect in deny, effect
for effect in ('ChronosPolymorphStun', 'ChaosStun', 'MedeaPoison', 'SheepSickSlow'):
    assert effect not in deny, effect

install = lua[lua.index('local function installInvincibility()'):lua.index('local function installHealth()')]
for token in ('AddEffectBlock', 'RemoveEffectBlock', 'ClearEffect', 'invincibilityBlockedEffects'):
    assert token in install, token
assert 'for _, effectName in ipairs(invincibilityBlockedEffects)' in install
assert 'AddEffectBlock({ Id = hero.ObjectId, Name = effectName })' in install
assert 'ClearEffect({ Id = hero.ObjectId, Name = effectName })' in install

damage_router = lua[lua.index('local function ensureHeroDamageRouter()'):lua.index('local function installInvincibility()')]
invincibility_branch_start = damage_router.index('if M.invincibility then')
invincibility_branch = damage_router[invincibility_branch_start:damage_router.index('end', invincibility_branch_start) + len('end')]
assert 'restoreInvincibilityHitCount(victim)' in invincibility_branch
assert invincibility_branch.index('restoreInvincibilityHitCount(victim)') < invincibility_branch.index('return nil')

assert 'M.invincibilityHitBaseline = hero.Hits' in install
assert 'M.invincibilityHitBaselineKnown = true' in install

release = lua[lua.index('local function releaseInvincibility()'):lua.index('local function releaseHealth()')]
assert 'for _, effectName in ipairs(invincibilityBlockedEffects)' in release
assert 'RemoveEffectBlock' in release
assert 'M.invincibilityEffectBlockHero = nil' in release
assert 'restoreInvincibilityHitCount(M.invincibilityHitHero)' in release
assert 'M.invincibilityHitBaselineKnown = false' in release

enforce = lua[lua.index('local function enforceLocks()'):lua.index('M.enforceLocksInternal = enforceLocks')]
assert 'restoreInvincibilityHitCount(CurrentRun.Hero)' in enforce

# Engine-level effect blocks cover effects applied by projectiles/terrain without
# installing a broad global ApplyEffect hook that could suppress player buffs.
assert 'installHook("ApplyEffect"' not in lua

print("invincibility_hostile_effects_ok")
