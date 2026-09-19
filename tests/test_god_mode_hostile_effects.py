from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
lua = (ROOT / "Backend/games/hades2/runtime/hades.lua").read_text()

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

release = lua[lua.index('local function releaseGodMode()'):lua.index('local function releaseHealth()')]
assert 'for _, effectName in ipairs(godModeBlockedEffects)' in release
assert 'RemoveEffectBlock' in release
assert 'M.godEffectBlockHero = nil' in release

# Engine-level effect blocks cover effects applied by projectiles/terrain without
# installing a broad global ApplyEffect hook that could suppress player buffs.
assert 'installHook("ApplyEffect"' not in lua

print("god_mode_hostile_effects_ok")
