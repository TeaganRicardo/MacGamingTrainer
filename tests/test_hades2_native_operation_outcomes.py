"""Native modal actions run on a game thread, and faults cross the shipped native callbacks and asynchronous action ledger."""

import ast
import subprocess
import tempfile
from pathlib import Path

from lua_runtime_support import RESIDENT_DISPATCH_CONTRACT, require_lua52

ROOT = Path(__file__).resolve().parents[1]
LUA = require_lua52("native operation outcome classification")


def fixture_literal(name, variable):
    tree = ast.parse((ROOT / "tests" / name).read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == variable
            for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError(variable)


BASE = fixture_literal("test_hades2_force_enable_rerolls.py", "HARNESS")
BASE = BASE[:BASE.index("assert(CurrentRun.NumRerolls == 10)")]
SELENE = fixture_literal("test_hades2_force_enable_rerolls_selene.py", "SELENE_CASES")
SELENE = SELENE[:SELENE.index("M.dispatch('set_feature'")]
STORE = fixture_literal("test_hades2_force_enable_rerolls_store_panels.py", "STORE_STUBS")

ASSERT_UNKNOWN = r'''
local observed = M.dispatch('status', { includeCatalogs = false })
assert(observed.runtimeOutcomeUnknown == true, 'post-native failure lost terminal trust evidence')
local ok, message = pcall(M.dispatch, 'set_rerolls', { amount = 77, requestId = 'later' })
assert(not ok and tostring(message):find('MGT_OUTCOME_UNKNOWN', 1, true),
  'post-native failure admitted another mutation')
'''

cases = {}
cases['rollback_owner_changed'] = BASE + r'''
M.dispatch('set_feature', { feature = 'forceEnableRerolls', value = true })
local source = copy(EnemyData.NPC_Artemis_Field_01)
source.Name, source.ObjectId = 'MacGamingTrainerSpecial_Artemis', -1
source.UpgradeOptions = { copy(basePool[1]), copy(basePool[2]), copy(basePool[3]) }
local screen = OpenUpgradeChoiceMenu(source)
local originalRun = CurrentRun
local replacementRun = copy(CurrentRun)
replacementRun.NumRerolls = 77
SetTraitsOnLoot = function(loot)
  CurrentRun = replacementRun
  loot.UpgradeOptions = {}
end
AttemptPanelReroll(screen, screen.Components.RerollButton)
assert(originalRun.NumRerolls == 9, 'native spend did not reach original owner')
assert(replacementRun.NumRerolls == 77, 'rollback refunded a replacement run')
''' + ASSERT_UNKNOWN
# AttemptPanelReroll itself is a game-owned yielding coroutine in 1.143476.
# Protect only the Trainer callback entered after native spend; the focused
# callback-stage cases below still require terminal unknown on unproven faults.
for stage, fault in {
    "candidates": "RemoveRandomValue = function() error('candidate generation fault') end",
    "clear": "local original = DestroyBoonLootButtons; DestroyBoonLootButtons = function(...) original(...); error('clear fault') end",
    "rebuild": "CreateBoonLootButtons = function() error('rebuild fault') end",
}.items():
    cases["upgrade_" + stage] = BASE + r'''
M.dispatch('set_feature', { feature = 'forceEnableRerolls', value = true })
local source = { Name = 'MacGamingTrainerSpecial_Arachne', ObjectId = -1,
  UpgradeOptions = { copy(basePool[1]), copy(basePool[2]), copy(basePool[3]) } }
local screen = OpenUpgradeChoiceMenu(source)
''' + fault + r'''
AttemptPanelReroll(screen, screen.Components.RerollButton)
local observed = M.dispatch('status', { includeCatalogs = false })
assert(not observed.activeFeatures.forceEnableRerolls, 'uncertain reroll still reported active')
assert(observed.featureErrors.forceEnableRerolls, 'uncertain reroll has no visible error')
assert(CurrentRun.NumRerolls == 9, 'unexpected fault guessed a refund')
''' + ASSERT_UNKNOWN

for stage, fault in {
    "candidates": "RemoveRandomValue = function() error('spell generation fault') end",
    "clear": "Destroy = function() error('spell clear fault') end",
    "rebuild": "CreateSpellButtons = function() error('spell rebuild fault') end",
}.items():
    cases["selene_" + stage] = BASE + SELENE + r'''
M.dispatch('set_feature', { feature = 'forceEnableRerolls', value = true })
SessionMapState.SelectedSpells = { 'SpellA', 'SpellB', 'SpellC' }
local screen = OpenSpellScreen({ Name = 'SpellDrop', ObjectId = 501 })
''' + fault + r'''
AttemptPanelReroll(screen, screen.Components.RerollButton)
''' + ASSERT_UNKNOWN

for stage, fault in {
    "candidates": "FillInShopOptions = function() error('shop candidate fault') end",
    "owner": "UpdateStoreOptionsDictionary = function() error('shop owner fault') end",
    "rebuild": "CreateSurfaceShopButtons = function() error('shop rebuild fault') end",
}.items():
    cases["surface_" + stage] = BASE.replace(
        "dofile(assert(arg[1]));", STORE + "\ndofile(assert(arg[1]));"
    ) + r'''
M.dispatch('set_feature', { feature = 'forceEnableRerolls', value = true })
local screen = { Name = 'SurfaceShop', Components = { ActionBar = { Id = 999 } }, KeepOpen = true }
ActiveScreens.SurfaceShop = screen
CreateSurfaceShopButtons(screen)
''' + fault + r'''
AttemptPanelReroll(screen, screen.Components.RerollButton)
''' + ASSERT_UNKNOWN

ASYNC = r'''
local pending
thread = function(fn) pending = fn end
AreScreensActive = function() return false end
ShowRerollUI = function() end
for _, name in ipairs({ 'AltAspectRatioFramesHide', 'OnScreenCloseStarted', 'SetAnimation',
  'UseableOff', 'CloseScreen', 'GetAllIds', 'OnScreenCloseFinished', 'ShowCombatUI',
  'SetPlayerVulnerable', 'SetupCostume' }) do _G[name] = function() end end
ScreenData.SellTraits = { ComponentData = { ActionBar = { Children = {
  CloseButton = { Data = {} } } } } }
local committed = false
'''
for command, params, native in (
    ("open_sell_traits", "{}", "OpenSellTraitMenu"),
    ("open_special_choice", "{ source = 'Arachne' }", "OpenUpgradeChoiceMenu"),
):
    cases[command] = BASE + ASYNC + f'''
{native} = function()
  committed = true
  CurrentRun.Hero.Health = 25
  error('native close fault after commit')
end
local params = {params}; params.requestId = 'modal'
local accepted = M.dispatch('{command}', params)
assert(accepted.actionOutcome == 'accepted')
assert(type(pending) == 'function')
pending()
local observed = M.dispatch('status', {{ includeCatalogs = false }})
assert(committed and CurrentRun.Hero.Health == 25)
assert(observed.lastAction.outcome == 'outcome_unknown', 'committed modal classified as known failure')
''' + ASSERT_UNKNOWN
    cases[command + '_stale_owner'] = BASE + ASYNC + f'''
{native} = function() committed = true end
local params = {params}; params.requestId = 'stale-modal'
assert(M.dispatch('{command}', params).actionOutcome == 'accepted')
CurrentRun = copy(CurrentRun)
pending()
local observed = M.dispatch('status', {{ includeCatalogs = false }})
assert(not committed, 'stale accepted action entered a replacement run')
assert(observed.lastAction.outcome == 'failed', 'pre-native owner refusal was not known')
assert(not observed.runtimeOutcomeUnknown)
'''

cases["sell_pre_native_refusal"] = BASE + ASYNC + r'''
OpenSellTraitMenu = function() error('must not enter native') end
M.dispatch('open_sell_traits', { requestId = 'pre-native' })
ScreenData.SellTraits.ComponentData.ActionBar.Children.CloseButton = nil
pending()
local observed = M.dispatch('status', { includeCatalogs = false })
assert(observed.lastAction.outcome == 'failed', 'pre-native refusal was classified unknown')
assert(not observed.runtimeOutcomeUnknown)
M.dispatch('set_rerolls', { amount = 77, requestId = 'safe' })
'''

for first_command, first_params in (
    ("open_sell_traits", "{}"),
    ("open_special_choice", "{ source = 'Arachne' }"),
):
    for second_command, second_params in (
        ("open_sell_traits", "{}"),
        ("open_special_choice", "{ source = 'Arachne' }"),
    ):
        cases[first_command + '_then_' + second_command] = BASE + ASYNC + f'''
local queued = {{}}
thread = function(fn) queued[#queued + 1] = fn end
local nativeCalls = 0
local function nativeMenu()
  nativeCalls = nativeCalls + 1
  if nativeCalls == 1 then error('native close fault after commit') end
end
OpenSellTraitMenu = nativeMenu
OpenUpgradeChoiceMenu = nativeMenu
local first = {first_params}; first.requestId = 'first-modal'
local second = {second_params}; second.requestId = 'second-modal'
assert(M.dispatch('{first_command}', first).actionOutcome == 'accepted')
assert(M.dispatch('{second_command}', second).actionOutcome == 'accepted')
assert(#queued == 2)
queued[1]()
assert(M.dispatch('status', {{ includeCatalogs = false }}).runtimeOutcomeUnknown)
queued[2]()
local observed = M.dispatch('status', {{ includeCatalogs = false }})
assert(nativeCalls == 1, 'queued action entered native after terminal outcome unknown')
assert(observed.lastAction.requestId == 'second-modal' and observed.lastAction.outcome == 'failed',
  'queued action that never entered native was not a known refusal')
''' + ASSERT_UNKNOWN

# The native sell screen yields, so it must open on a game thread, never inside
# the debugger dispatch, and it must leave the shared screen definition intact.
cases["sell_screen_lifecycle"] = BASE + ASYNC + r'''
local original = ScreenData.SellTraits
local entered, seenScreen, closeName
OpenSellTraitMenu = function()
  entered = true
  seenScreen = ScreenData.SellTraits
  closeName = seenScreen.ComponentData.ActionBar.Children.CloseButton.Data.OnPressedFunctionName
end
assert(M.dispatch('open_sell_traits', { requestId = 'sell' }).actionOutcome == 'accepted')
assert(not entered, 'native sell screen opened inside the debugger dispatch')
assert(type(pending) == 'function', 'native sell screen was not deferred to a game thread')
pending()
assert(entered, 'native sell screen never opened')
assert(seenScreen ~= original, 'native sell screen used the shared screen definition')
assert(closeName == 'MacGamingTrainerCloseSellTraitScreen', 'sell screen close button not routed to the Trainer close')
assert(ScreenData.SellTraits == original, 'shared sell screen definition was not restored')
assert(original.ComponentData.ActionBar.Children.CloseButton.Data.OnPressedFunctionName == nil,
  'shared sell screen close button was rewritten')
local observed = M.dispatch('status', { includeCatalogs = false })
assert(observed.lastAction.outcome ~= 'outcome_unknown' and observed.lastAction.outcome ~= 'failed')
assert(not observed.runtimeOutcomeUnknown)

-- Outside a store the Trainer close tears the screen down itself and never
-- fabricates Store state; inside a store it hands over to the game's close.
local calls, usedIds = {}, nil
for _, name in ipairs({ 'UseableOff', 'AltAspectRatioFramesHide', 'OnScreenCloseStarted',
  'CloseScreen', 'OnScreenCloseFinished', 'ShowCombatUI', 'SetPlayerVulnerable' }) do
  _G[name] = function(args)
    calls[#calls + 1] = name
    if name == 'UseableOff' then usedIds = args.Ids end
  end
end
CloseStoreScreen = function() error('no store is open') end
CurrentRun.CurrentRoom.Store = nil
local screen = { Name = 'SellTraitScreen',
  Components = { PurchaseButton1 = { Id = 11 }, PurchaseButton2 = { Id = 12 }, CloseButton = { Id = 13 } } }
MacGamingTrainerCloseSellTraitScreen(screen, {})
assert(table.concat(calls, ',') == 'UseableOff,AltAspectRatioFramesHide,OnScreenCloseStarted,'
  .. 'CloseScreen,OnScreenCloseFinished,ShowCombatUI,SetPlayerVulnerable', table.concat(calls, ','))
assert(#usedIds == 2, 'sell screen purchase buttons stayed usable')
assert(CurrentRun.CurrentRoom.Store == nil, 'Trainer close fabricated Store state')
local storeClosed
CurrentRun.CurrentRoom.Store = { StoreOptions = {} }
CloseStoreScreen = function(closing) storeClosed = closing end
MacGamingTrainerCloseSellTraitScreen(screen, {})
assert(storeClosed == screen, 'sell screen inside a store did not use the native store close')
'''

# Echo's choice reads the run's last reward. The Trainer lends a synthetic one
# only while the native menu runs and never overwrites a real one.
cases["echo_last_reward"] = BASE + ASYNC + r'''
local seen
OpenUpgradeChoiceMenu = function() seen = CurrentRun.LastReward end
CurrentRun.LastReward = nil
assert(M.dispatch('open_special_choice', { source = 'Echo', requestId = 'echo-empty' }).actionOutcome == 'accepted')
pending()
assert(seen and seen.Name == 'MaxHealthDrop', 'Echo choice opened without a last reward')
assert(CurrentRun.LastReward == nil, 'Echo choice leaked its synthetic last reward')

local real = { Type = 'Boon', Name = 'RealReward' }
CurrentRun.LastReward = real
assert(M.dispatch('open_special_choice', { source = 'Echo', requestId = 'echo-real' }).actionOutcome == 'accepted')
pending()
assert(seen == real and CurrentRun.LastReward == real, 'Echo choice replaced the run last reward')

CurrentRun.LastReward = nil
OpenUpgradeChoiceMenu = function() seen = CurrentRun.LastReward; error('native fault') end
M.dispatch('open_special_choice', { source = 'Echo', requestId = 'echo-fault' })
pending()
assert(seen and seen.Name == 'MaxHealthDrop')
assert(CurrentRun.LastReward == nil, 'Echo choice kept its synthetic last reward after a native fault')
'''

# A special-blessing choice leaves no trace of the Trainer's synthetic loot in
# the run: its history entries and loot pickup are rolled back.
cases["special_choice_history"] = BASE + ASYNC + r'''
OpenUpgradeChoiceMenu = function(source)
  CurrentRun.LootChoiceHistory = CurrentRun.LootChoiceHistory or {}
  table.insert(CurrentRun.LootChoiceHistory, { Name = source.Name })
  GameState.LootPickups[source.Name] = 1
end
CurrentRun.LootChoiceHistory = nil
M.dispatch('open_special_choice', { source = 'Arachne', requestId = 'history-absent' })
pending()
assert(CurrentRun.LootChoiceHistory == nil, 'special choice left a synthetic run history')
local history = { { Name = 'RealChoice' } }
CurrentRun.LootChoiceHistory = history
M.dispatch('open_special_choice', { source = 'Arachne', requestId = 'history-present' })
pending()
assert(CurrentRun.LootChoiceHistory == history and #history == 1 and history[1].Name == 'RealChoice',
  'special choice changed the run history')
assert(GameState.LootPickups.MacGamingTrainerSpecial_Arachne == nil, 'special choice left a synthetic loot pickup')
'''

with tempfile.TemporaryDirectory(prefix="mgt-native-outcomes-") as temporary:
    for name, source in cases.items():
        harness = Path(temporary) / (name + ".lua")
        harness.write_text(source)
        result = subprocess.run(
            [LUA, str(harness), str(ROOT / "Backend/games/hades2/runtime/hades.lua"),
             str(RESIDENT_DISPATCH_CONTRACT)],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, name + "\n" + result.stdout + result.stderr

print("hades2_native_operation_outcomes_ok")
