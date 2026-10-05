import subprocess
import tempfile
from pathlib import Path

from lua_runtime_support import RESIDENT_DISPATCH_CONTRACT, require_lua52

ROOT = Path(__file__).resolve().parents[1]
LUA = require_lua52('native UpgradeChoice reroll behavior')

HARNESS = r'''
SessionState = {}; SessionMapState = {}
GameState = { Resources = {}, LifetimeResourcesGained = {}, RunHistory = {}, LootPickups = {} }
ResourceData = {}; ResourceDisplayOrderData = {}; TraitElementData = {}
LootData = {}; ConsumableData = {}; RewardStoreData = {}; ScreenData = {}
MapState = { RoomRequiredObjects = {} }; LootObjects = {}; CodexOrdering = { OlympianGods = {}, Order = {} }
UpdateTimers = function() end
CurrentRun = {
  Hero = { ObjectId = 1, Health = 100, MaxHealth = 100, Mana = 50, MaxMana = 50,
    Traits = {}, TraitDictionary = {}, Elements = {}, BoonData = {} },
  CurrentRoom = {}, NumRerolls = 10, PickedTraits = {}, BannedTraits = {},
}
ScreenState = {}; ScreenAnchors = {}; ActiveScreens = {}
RerollCosts = { Boon = 1, Hammer = -1, ReuseIncrement = 1 }
TraitData = {}
for _, name in ipairs({ 'CostumeA', 'CostumeB', 'CostumeC', 'CostumeD', 'CostumeE' }) do
  TraitData[name] = { Name = name, RarityLevels = { Common = {} } }
end
EnemyData = { NPC_Arachne_01 = { Name = 'NPC_Arachne_01' } }
PresetEventArgs = { ArachneCostumeChoices = { UpgradeOptions = {} } }
for _, name in ipairs({ 'CostumeA', 'CostumeB', 'CostumeC', 'CostumeD', 'CostumeE' }) do
  table.insert(PresetEventArgs.ArachneCostumeChoices.UpgradeOptions, { ItemName = name, Type = 'Trait', Rarity = 'Common' })
end
local function copy(value)
  if type(value) ~= 'table' then return value end
  local result = {}; for key, item in pairs(value) do result[key] = copy(item) end; return result
end
DeepCopyTable = copy; ShallowCopyTable = copy
IsGameStateEligible = function() return true end
HeroHasTrait = function(name) return CurrentRun.Hero.TraitDictionary[name] ~= nil end
PassRarityCheck = function() return true end
RemoveRandomValue = function(values) return table.remove(values, 1) end
GetRandomValue = function(values) return values[1] end
RandomSynchronize = function() end
local pending = {}
wait = function() coroutine.yield() end
thread = function(fn, ...)
  local co = coroutine.create(fn); local ok, message = coroutine.resume(co, ...)
  assert(ok, message)
  if coroutine.status(co) ~= 'dead' then table.insert(pending, co) end
  return co
end
local function finish()
  while #pending > 0 do
    local co = table.remove(pending, 1); local ok, message = coroutine.resume(co)
    assert(ok, message)
    if coroutine.status(co) ~= 'dead' then table.insert(pending, co) end
  end
end
local inputBlocked = false
AddInputBlock = function() inputBlocked = true end
RemoveInputBlock = function() inputBlocked = false end
HideTopMenuScreenTooltips = function() end
UpdateRerollUI = function() end
InvalidateCheckpoint = function() end
IncrementTableValue = function(values, key, amount) values[key] = (values[key] or 0) + amount end
CannotRerollPanelPresentation = function() error('unaffordable native attempt') end
PreRerollPanelPresentation = function() wait(0.51) end
PostRerollPanelPresentation = function() end
CallFunctionName = function(name, ...) return assert(_G[name], 'missing callback lease')(... ) end
-- The native InteractLogic contract spends before its yielding presentation,
-- dispatches a named callback, and owns input/transition cleanup afterwards.
AttemptPanelReroll = function(screen, button)
  local cost = button.Cost
  if not cost or ScreenState.InTransition then return end
  if CurrentRun.NumRerolls < cost or cost < 0 then CannotRerollPanelPresentation(button); return end
  AddInputBlock({ Name = 'AttemptPanelReroll' }); HideTopMenuScreenTooltips({})
  CurrentRun.NumRerolls = CurrentRun.NumRerolls - cost
  CurrentRun.CurrentRoom.SpentRerolls = CurrentRun.CurrentRoom.SpentRerolls or {}
  if button.RerollId then IncrementTableValue(CurrentRun.CurrentRoom.SpentRerolls, button.RerollId, 1) end
  UpdateRerollUI(CurrentRun.NumRerolls); RandomSynchronize(CurrentRun.NumRerolls); InvalidateCheckpoint()
  ScreenState.InTransition = true; PreRerollPanelPresentation(screen, button)
  CallFunctionName(button.RerollFunctionName, screen, button)
  PostRerollPanelPresentation(screen, button)
  wait(0.1); RemoveInputBlock({ Name = 'AttemptPanelReroll' }); wait(0.95)
  ScreenState.InTransition = false
end
local nativeFallbacks = 0
RerollBoonLoot = function() nativeFallbacks = nativeFallbacks + 1; error('fixed NPC fell through generic generator') end
DestroyBoonLootButtons = function(screen) screen.UpgradeButtons = {} end
CreateBoonLootButtons = function(screen, source)
  screen.UpgradeButtons = {}
  for _, option in ipairs(source.UpgradeOptions) do
    table.insert(screen.UpgradeButtons, { Data = { Name = option.ItemName, Rarity = option.Rarity }, LootData = source, OnPressedFunctionName = 'HandleUpgradeChoiceSelection' })
  end
end
ModifyTextBox = function() end
HandleUpgradeChoiceSelection = function(screen, button)
  screen.ChoiceMade = true
  CurrentRun.Hero.TraitDictionary[button.Data.Name] = { Name = button.Data.Name }
  ActiveScreens.UpgradeChoice = nil; ScreenAnchors.ChoiceScreen = nil
end
local source = copy(EnemyData.NPC_Arachne_01)
source.ObjectId = 42; source.BlockReroll = true
source.UpgradeOptions = { copy(PresetEventArgs.ArachneCostumeChoices.UpgradeOptions[1]),
  copy(PresetEventArgs.ArachneCostumeChoices.UpgradeOptions[2]), copy(PresetEventArgs.ArachneCostumeChoices.UpgradeOptions[3]) }
local screen = { Name = 'UpgradeChoice', Source = source, Components = {
  RerollButton = { Id = 99, Cost = -1, LootData = source, RerollId = 42, RerollFunctionName = 'RerollBoonLoot' },
  RerollIcon = { Id = 100 },
}, OnCloseFinishedFunctionName = 'ArachneArmorApply' }
ActiveScreens.UpgradeChoice = screen; ScreenAnchors.ChoiceScreen = screen
CreateBoonLootButtons(screen, source)
dofile(assert(arg[1])); dofile(assert(arg[2]))
local M = __MacGamingTrainerV1
local observed = M.dispatch('status', { includeCatalogs = false }).choiceReroll
assert(observed and observed.available and observed.cost == 1 and type(observed.menuToken) == 'string',
  'formerly forbidden fixed NPC did not expose one observed native reroll')
local result = M.dispatch('reroll_choice', { requestId = 'fixed-reroll-1', menuToken = observed.menuToken,
  expectedCost = 1, includeCatalogs = false })
assert(result.actionOutcome == 'accepted' and CurrentRun.NumRerolls == 9)
assert(source.UpgradeOptions[1].ItemName == 'CostumeA', 'candidate commit ran before native callback')
finish()
local completed = M.dispatch('status', { includeCatalogs = false })
assert(completed.lastAction.outcome == 'completed' and completed.choiceReroll.cost == 2)
assert(not inputBlocked and not ScreenState.InTransition, 'native reroll cleanup was skipped')
assert(nativeFallbacks == 0 and screen.OnCloseFinishedFunctionName == 'ArachneArmorApply')
assert(source.UpgradeOptions[3].ItemName == 'CostumeD', 'reroll did not present a changed eligible candidate')
HandleUpgradeChoiceSelection(screen, screen.UpgradeButtons[3])
assert(CurrentRun.Hero.TraitDictionary.CostumeD, 'native selection did not acquire the displayed candidate')
local duplicate = M.dispatch('reroll_choice', { requestId = 'fixed-reroll-1', menuToken = observed.menuToken,
  expectedCost = 1, includeCatalogs = false })
assert(duplicate.duplicate and duplicate.actionOutcome == 'completed' and CurrentRun.NumRerolls == 9,
  'closed menu defeated deduplication or spent twice')
-- A post-presentation failure must never publish completion. Before the
-- adapter gets a Refresh reply, a DIFFERENT mutation must already be blocked.
screen.ChoiceMade = nil; ActiveScreens.UpgradeChoice = screen; ScreenAnchors.ChoiceScreen = screen
source.UpgradeOptions = { copy(PresetEventArgs.ArachneCostumeChoices.UpgradeOptions[1]),
  copy(PresetEventArgs.ArachneCostumeChoices.UpgradeOptions[2]), copy(PresetEventArgs.ArachneCostumeChoices.UpgradeOptions[3]) }
CreateBoonLootButtons(screen, source)
PostRerollPanelPresentation = function() error('post presentation failed after candidate commit') end
local unknownObserved = M.dispatch('status', { includeCatalogs = false }).choiceReroll
local unknownAccepted = M.dispatch('reroll_choice', { requestId = 'post-failure', menuToken = unknownObserved.menuToken,
  expectedCost = unknownObserved.cost, includeCatalogs = false })
assert(unknownAccepted.actionOutcome == 'accepted')
finish()
local blocked, failure = pcall(M.dispatch, 'set_rerolls', { requestId = 'different-after-unknown', amount = 50, includeCatalogs = false })
assert(not blocked and tostring(failure):find('MGT_OUTCOME_UNKNOWN', 1, true),
  'resident allowed a new mutation before asynchronous unknown was observed by the adapter')
local uncertain = M.dispatch('status', { includeCatalogs = false })
assert(uncertain.lastAction.outcome == 'outcome_unknown' and uncertain.rerolls == 7)
print('hades2_choice_reroll_runtime_ok')
'''

CASES = {'natural_and_unknown': HARNESS,
 'same_content_new_options': HARNESS.split('local observed =')[0] + r'''
local observed = M.dispatch('status', { includeCatalogs = false }).choiceReroll
source.UpgradeOptions = copy(source.UpgradeOptions)
local ok = pcall(M.dispatch, 'reroll_choice', { requestId = 'new-options', menuToken = observed.menuToken,
  expectedCost = observed.cost, includeCatalogs = false })
assert(not ok and CurrentRun.NumRerolls == 10, 'new options table with same contents accepted a stale menu token')
print('hades2_choice_reroll_runtime_ok')
''',
 'same_hero_owned_before_spend': HARNESS.split('local observed =')[0] + r'''
local observed = M.dispatch('status', { includeCatalogs = false }).choiceReroll
CurrentRun.Hero.TraitDictionary.CostumeD = { Name = 'CostumeD' }
local ok = pcall(M.dispatch, 'reroll_choice', { requestId = 'owned-before-spend', menuToken = observed.menuToken,
  expectedCost = observed.cost, includeCatalogs = false })
assert(not ok and CurrentRun.NumRerolls == 10, 'same Hero changed eligibility before spending')
print('hades2_choice_reroll_runtime_ok')
''',
 'same_hero_owned_after_spend': HARNESS.split('local observed =')[0] + r'''
local observed = M.dispatch('status', { includeCatalogs = false }).choiceReroll
M.dispatch('reroll_choice', { requestId = 'owned-after-spend', menuToken = observed.menuToken,
  expectedCost = observed.cost, includeCatalogs = false })
CurrentRun.Hero.TraitDictionary.CostumeD = { Name = 'CostumeD' }
finish()
local result = M.dispatch('status', { includeCatalogs = false })
assert(result.lastAction.outcome == 'outcome_unknown' and CurrentRun.NumRerolls == 9
  and source.UpgradeOptions[1].ItemName == 'CostumeA', 'same Hero changed eligibility during native wait and committed stale candidates')
assert(not inputBlocked and not ScreenState.InTransition, 'callback rejection bypassed native cleanup')
print('hades2_choice_reroll_runtime_ok')
'''}

FAMILY_SETUP = r'''
local function show(value)
  value.Traits = value.Traits or { 'ChoiceA', 'ChoiceB', 'ChoiceC', 'ChoiceD', 'ChoiceE' }
  source = value
  screen = { Name = 'UpgradeChoice', Source = source, Components = {
    RerollButton = { Id = 99, Cost = -1, LootData = source, RerollId = source.ObjectId, RerollFunctionName = 'RerollBoonLoot' },
    RerollIcon = { Id = 100 },
  }, OnCloseFinishedFunctionName = 'nativeOuterPost' }
  ActiveScreens.UpgradeChoice = screen; ScreenAnchors.ChoiceScreen = screen
  CreateBoonLootButtons(screen, source)
  return screen
end
local function finishAction(id)
  for _ = 1, 20 do
    local count = #pending
    for _ = 1, count do
      local co = table.remove(pending, 1); local ok, message = coroutine.resume(co); assert(ok, message)
      if coroutine.status(co) ~= 'dead' then table.insert(pending, co) end
    end
    if M.requests[id].status ~= 'accepted' then return end
  end
  error('reroll failed to reach a terminal receipt')
end
CreateBoonLootButtons = function(s, value)
  s.UpgradeButtons = {}
  for _, option in ipairs(value.UpgradeOptions) do
    local data = copy(option); data.Name = option.ItemName
    if option.Type == 'TransformingTrait' then data.Name = option.SecondaryItemName; data.OnExpire = { TraitData = { Name = option.ItemName } } end
    table.insert(s.UpgradeButtons, { Data = data, LootData = value,
      OnPressedFunctionName = value.OnPressedFunctionNameOverride or 'HandleUpgradeChoiceSelection' })
  end
end
HandleUpgradeChoiceSelection = function(s, button)
  local data = button.Data
  if data.Type == 'TransformingTrait' then
    CurrentRun.Hero.TraitDictionary[data.Name] = copy(data)
  else
    local prior = CurrentRun.Hero.TraitDictionary[data.Name]
    CurrentRun.Hero.TraitDictionary[data.Name] = { Name = data.Name, Rarity = data.Rarity, StackNum = prior and (prior.StackNum or 1) + 1 or 1 }
  end
  s.ChoiceMade = true; ActiveScreens.UpgradeChoice = nil; ScreenAnchors.ChoiceScreen = nil
end
SelectEchoBoon = HandleUpgradeChoiceSelection
AreScreensActive = function() return next(ActiveScreens) ~= nil end
OpenUpgradeChoiceMenu = function(value)
  local s = show(value)
  while not s.ChoiceMade do wait() end
end
SetupCostume = function() end
GetProcessedTraitData = function(args) return { Name = args.TraitName, StackNum = args.StackNum, ExtractData = {} } end
SetTraitTextData = function(value) value.ExtractData = value.ExtractData or {} end
GetHeroTrait = function(name) return CurrentRun.Hero.TraitDictionary[name] end
IsGodTrait = function(name, args) return not name:find('NotGod') end
IsTraitEligible = function(data, args)
  return data and not data.Ineligible and (not CurrentRun.BannedTraits[data.Name] or (args and args.AllowBannedTraits))
end
HeroSlotFilled = function(slot) return slot == 'occupied' end
local pool = {}
for _, name in ipairs({ 'ChoiceA', 'ChoiceB', 'ChoiceC', 'ChoiceD', 'ChoiceE' }) do
  TraitData[name] = { Name = name, RarityLevels = { Common = {} } }
  pool[#pool + 1] = { ItemName = name, Type = 'Trait', Rarity = 'Common' }
end
local expectedNativeName
GetEligibleUpgrades = function(_, value)
  local result = {}
  for _, name in ipairs(value.Traits or value.WeaponUpgrades or {}) do
    if (value.StackOnly or not HeroHasTrait(name)) and (value.StripRequirements or IsTraitEligible(TraitData[name], { AllowBannedTraits = value.StackOnly })) then
      result[#result + 1] = { ItemName = name, Type = 'Trait' }
    end
  end
  return result
end
GetEligibleTransformingTrait = function(names)
  local result = {}; for _, name in ipairs(names) do if IsTraitEligible(TraitData[name]) then result[#result + 1] = name end end; return result
end
SetTraitsOnLoot = function(value, args)
  value.Traits = value.Traits or { 'ChoiceA', 'ChoiceB', 'ChoiceC', 'ChoiceD', 'ChoiceE' }
  assert(value.Name == expectedNativeName, 'native eligibility saw a synthetic or wrong source.Name')
  if value.Name == 'WeaponUpgrade' then assert(CurrentRun.Hero.Weapons.WeaponAxe, 'Hammer lost native weapon/aspect context') end
  if value.Name == 'StackUpgrade' then assert(value.StackOnly and HeroHasTrait('ChoiceD'), 'StackOnly lost native owned-trait context') end
  if value.Name == 'TrialUpgrade' then assert(value.TransformingTraits and HeroHasTrait('ChoiceD'), 'Chaos lost native owned-repeat eligibility') end
  value.UpgradeOptions = {}
  for _, option in ipairs(pool) do
    if not (args and args.ExclusionNames and option.ItemName == args.ExclusionNames[1]) then
      value.UpgradeOptions[#value.UpgradeOptions + 1] = copy(option)
      if #value.UpgradeOptions == 3 then break end
    end
  end
end
local function rerollAndSelect(id)
  local observed = M.dispatch('status', { includeCatalogs = false }).choiceReroll
  assert(observed.available and observed.cost == 1, id .. ' missing observed native cost')
  local old = source.UpgradeOptions
  local accepted = M.dispatch('reroll_choice', { requestId = id, menuToken = observed.menuToken, expectedCost = 1, includeCatalogs = false })
  assert(accepted.actionOutcome == 'accepted' and CurrentRun.NumRerolls == 9 and source.UpgradeOptions == old)
  finishAction(id)
  assert(M.requests[id].status == 'completed' and not inputBlocked and not ScreenState.InTransition, id .. ' did not complete native unwind')
  local next = M.dispatch('status', { includeCatalogs = false }).choiceReroll
  assert(next.cost == 2 and next.menuToken ~= observed.menuToken, 'candidate commit did not advance observation/cost')
  assert(source.UpgradeOptions ~= old and screen.OnCloseFinishedFunctionName == 'nativeOuterPost')
  assert(nativeFallbacks == 0 and CurrentRun.CurrentRoom.SpentRerolls[-1] == nil, 'shared synthetic cost or generic fallback')
  local button = screen.UpgradeButtons[3]
  CallFunctionName(button.OnPressedFunctionName, screen, button)
  assert(CurrentRun.Hero.TraitDictionary[button.Data.Name], 'displayed candidate not acquired natively')
  finish()
  local duplicate = M.dispatch('reroll_choice', { requestId = id, menuToken = observed.menuToken, expectedCost = 1, includeCatalogs = false })
  assert(duplicate.duplicate and duplicate.actionOutcome == 'completed' and CurrentRun.NumRerolls == 9)
end
ActiveScreens = {}; ScreenAnchors.ChoiceScreen = nil
'''

fixed = {
    'Arachne': ('NPC_Arachne_01', 'ArachneCostumeChoices'),
    'Narcissus': ('NPC_Narcissus_01', 'NarcissusBenefitChoices'),
    'Echo': ('NPC_Echo_01', 'EchoBenefitChoices'),
    'Medea': ('NPC_Medea_01', 'MedeaCurseChoices'),
    'Circe': ('NPC_Circe_01', 'CirceBlessingChoices'),
    'Icarus': ('NPC_Icarus_01', 'IcarusBenefitChoices'),
}
loot_npc = {'Artemis': 'NPC_Artemis_Field_01', 'Athena': 'NPC_Athena_01', 'Dionysus': 'NPC_Dionysus_01', 'Hades': 'NPC_Hades_Field_01'}
prefix = HARNESS.split('local observed =')[0] + FAMILY_SETUP
for family, (npc, choices) in fixed.items():
    setup = f"EnemyData.{npc} = {{ Name = '{npc}' }}; PresetEventArgs.{choices} = {{ UpgradeOptions = copy(pool) }}\n"
    for trainer_opened in (False, True):
        opening = (f"M.dispatch('open_special_choice', {{ requestId = 'open-{family}', source = '{family}', includeCatalogs = false }})\n"
                   if trainer_opened else f"local value = copy(EnemyData.{npc}); value.ObjectId = 42; value.BlockReroll = true; value.UpgradeOptions = {{ copy(pool[1]), copy(pool[2]), copy(pool[3]) }}; show(value)\n")
        CASES[f'{family}_{"trainer" if trainer_opened else "natural"}'] = prefix + setup + opening + f"rerollAndSelect('{family}-reroll'); print('hades2_choice_reroll_runtime_ok')"
for family, npc in loot_npc.items():
    setup = f"EnemyData.{npc} = {{ Name = '{npc}' }}; expectedNativeName = '{npc}'\n"
    for trainer_opened in (False, True):
        opening = (f"M.dispatch('open_special_choice', {{ requestId = 'open-{family}', source = '{family}', includeCatalogs = false }})\n"
                   if trainer_opened else f"local value = copy(EnemyData.{npc}); value.ObjectId = 42; value.UpgradeOptions = {{ copy(pool[1]), copy(pool[2]), copy(pool[3]) }}; show(value)\n")
        CASES[f'{family}_{"trainer" if trainer_opened else "natural"}'] = prefix + setup + opening + f"rerollAndSelect('{family}-reroll'); print('hades2_choice_reroll_runtime_ok')"
for family in ('WeaponUpgrade', 'TrialUpgrade', 'StackUpgrade', 'ZeusUpgrade', 'HermesUpgrade'):
    CASES[family] = prefix + f"expectedNativeName = '{family}'\n" + r'''
local value = { Name = expectedNativeName, ObjectId = 42, UpgradeOptions = { copy(pool[1]), copy(pool[2]), copy(pool[3]) } }
value.Traits = { 'ChoiceA', 'ChoiceB', 'ChoiceC', 'ChoiceD', 'ChoiceE' }
CurrentRun.Hero.Weapons = { WeaponAxe = true }
if expectedNativeName == 'TrialUpgrade' then
  value.TransformingTraits = true
  value.PermanentTraits = value.Traits; value.TemporaryTraits = { 'CurseB' }; TraitData.CurseB = { Name = 'CurseB' }
  CurrentRun.Hero.TraitDictionary.ChoiceD = { Name = 'ChoiceD' }
  for _, option in ipairs(pool) do option.Type = 'TransformingTrait'; option.SecondaryItemName = 'CurseB' end
  value.UpgradeOptions = { copy(pool[1]), copy(pool[2]), copy(pool[3]) }
elseif expectedNativeName == 'StackUpgrade' then
  value.StackOnly = true; CurrentRun.Hero.TraitDictionary.ChoiceD = { Name = 'ChoiceD', StackNum = 2 }
  CurrentRun.BannedTraits.ChoiceD = true -- native StackOnly explicitly permits this owned banned trait
  for _, option in ipairs(pool) do if option.ItemName ~= 'ChoiceD' then CurrentRun.Hero.TraitDictionary[option.ItemName] = { Name = option.ItemName, StackNum = 1 } end end
elseif expectedNativeName == 'HermesUpgrade' then LootData.HermesUpgrade = { GodLoot = false, TreatAsGodLootByShops = true }
else LootData[expectedNativeName] = { GodLoot = true } end
show(value)
rerollAndSelect(expectedNativeName)
if expectedNativeName == 'StackUpgrade' then assert(CurrentRun.Hero.TraitDictionary.ChoiceD.StackNum == 3) end
if expectedNativeName == 'TrialUpgrade' then assert(CurrentRun.Hero.TraitDictionary.CurseB.OnExpire.TraitData.Name == 'ChoiceD') end
print('hades2_choice_reroll_runtime_ok')
'''
CASES['Echo_previous_run'] = prefix + r'''
GameState.RunHistory = { { TraitRarityCache = { ChoiceA = 'Common', ChoiceB = 'Rare', ChoiceC = 'Epic', ChoiceD = 'Common', ChoiceE = 'Common', NotGod = 'Common', Blocked = 'Rare', Owned = 'Rare', Slotted = 'Rare' } } }
TraitData.NotGod = {}; TraitData.Blocked = { Ineligible = true }; TraitData.Owned = {}; TraitData.Slotted = { Slot = 'occupied' }
CurrentRun.Hero.TraitDictionary.Owned = { Name = 'Owned' }
CurrentRun.Hero.TraitDictionary.ElementalRarityUpgradeBoon = { Activated = true }
show({ Name = 'NPC_Echo_01', ObjectId = -1, MenuTitle = 'EchoChoiceMenu_LastRun', OnPressedFunctionNameOverride = 'SelectEchoBoon',
  UpgradeOptions = { copy(pool[1]), copy(pool[2]), copy(pool[3]) } })
local observed = M.dispatch('status', { includeCatalogs = false }).choiceReroll
M.dispatch('reroll_choice', { requestId = 'previous-run', menuToken = observed.menuToken, expectedCost = 1, includeCatalogs = false })
finishAction('previous-run')
assert(M.requests['previous-run'].status == 'completed' and source.OnPressedFunctionNameOverride == 'SelectEchoBoon')
for _, option in ipairs(source.UpgradeOptions) do assert(option.ItemName ~= 'NotGod' and option.ItemName ~= 'Blocked' and option.ItemName ~= 'Owned' and option.ItemName ~= 'Slotted' and option.Rarity ~= 'Common') end
CallFunctionName(screen.UpgradeButtons[1].OnPressedFunctionName, screen, screen.UpgradeButtons[1])
assert(CurrentRun.Hero.TraitDictionary[screen.UpgradeButtons[1].Data.Name], 'Echo selected displayed historical boon using special native selector')
print('hades2_choice_reroll_runtime_ok')
'''


for change_name, change in {
 'picked': "CurrentRun.PickedTraits.CostumeD = true",
 'requirement': "PresetEventArgs.ArachneCostumeChoices.UpgradeOptions[4].GameStateRequirements.flag = false",
}.items():
 for phase in ('before', 'after'):
    setup = r'''
PresetEventArgs.ArachneCostumeChoices.UpgradeOptions[4].GameStateRequirements = { flag = true }
IsGameStateEligible = function(value, requirements) assert(value.Name == 'NPC_Arachne_01'); return requirements.flag end
local observed = M.dispatch('status', { includeCatalogs = false }).choiceReroll
local params = { requestId = 'eligibility-change', menuToken = observed.menuToken, expectedCost = observed.cost, includeCatalogs = false }
'''
    body = (change + "\nlocal ok = pcall(M.dispatch, 'reroll_choice', params); assert(not ok and CurrentRun.NumRerolls == 10)"
            if phase == 'before' else "M.dispatch('reroll_choice', params)\n" + change + r'''
finish()
assert(M.dispatch('status', { includeCatalogs = false }).lastAction.outcome == 'outcome_unknown')
assert(source.UpgradeOptions[1].ItemName == 'CostumeA' and CurrentRun.NumRerolls == 9 and not inputBlocked and not ScreenState.InTransition)
''')
    CASES[f'{change_name}_{phase}_spend'] = HARNESS.split('local observed =')[0] + setup + body + "\nprint('hades2_choice_reroll_runtime_ok')"

CIRCE_SETUP = prefix + r'''
TraitData.DoubleFamiliarTrait = { RarityLevels = { Common = { Multiplier = 1 } } }
TraitData.FamiliarCat = { CirceBonusStacks = 3, CirceStatLine = 'catPreview' }
pool[2].ItemName = 'DoubleFamiliarTrait'
local familiar = { Name = 'FamiliarCat', StackNum = 2, FamiliarTrait = true, FamiliarLastStandHealAmount = 20 }
CurrentRun.Hero.Traits = { familiar }
PresetEventArgs.CirceBlessingChoices = { UpgradeOptions = copy(pool) }
SessionMapState.OldFamiliarTrait = { sentinel = 'old' }; SessionMapState.NewFamiliarTrait = { sentinel = 'new' }; SessionMapState.StatLine = 'oldLine'
local previousOld, previousNew = SessionMapState.OldFamiliarTrait, SessionMapState.NewFamiliarTrait
show({ Name = 'NPC_Circe_01', ObjectId = 42, UpgradeOptions = { copy(pool[1]), copy(pool[2]), copy(pool[3]) } })
local observed = M.dispatch('status', { includeCatalogs = false }).choiceReroll
local params = { requestId = 'circe-preview', menuToken = observed.menuToken, expectedCost = 1, includeCatalogs = false }
'''
CASES['circe_preview_and_obsolete_clear'] = CIRCE_SETUP + r'''
M.dispatch('reroll_choice', params)
assert(SessionMapState.OldFamiliarTrait == previousOld and SessionMapState.NewFamiliarTrait == previousNew, 'preview changed before callback')
finishAction('circe-preview')
assert(M.requests['circe-preview'].status == 'completed')
assert(SessionMapState.OldFamiliarTrait.StackNum == 2 and SessionMapState.NewFamiliarTrait.StackNum == 7 and SessionMapState.StatLine == 'catPreview')
assert(SessionMapState.OldFamiliarTrait.ExtractData.TooltipLastStandAmount == 1 and SessionMapState.NewFamiliarTrait.ExtractData.TooltipLastStandAmount == 2)
assert(familiar.ExtractData == nil, 'staging mutated live familiar')
observed = M.dispatch('status', { includeCatalogs = false }).choiceReroll
M.dispatch('reroll_choice', { requestId = 'circe-no-double', menuToken = observed.menuToken, expectedCost = 2, includeCatalogs = false })
finishAction('circe-no-double')
assert(M.requests['circe-no-double'].status == 'completed' and SessionMapState.OldFamiliarTrait == nil and SessionMapState.NewFamiliarTrait == nil and SessionMapState.StatLine == nil)
print('hades2_choice_reroll_runtime_ok')
'''
for phase in ('before', 'after'):
    body = ("familiar.StackNum = 3\nlocal ok = pcall(M.dispatch, 'reroll_choice', params); assert(not ok and CurrentRun.NumRerolls == 10)"
            if phase == 'before' else r'''
M.dispatch('reroll_choice', params)
familiar.StackNum = 3
finishAction('circe-preview')
assert(M.requests['circe-preview'].status == 'outcome_unknown' and source.UpgradeOptions[1].ItemName == 'ChoiceA' and CurrentRun.NumRerolls == 9)
''')
    CASES[f'circe_familiar_{phase}_spend'] = CIRCE_SETUP + body + r'''
assert(SessionMapState.OldFamiliarTrait == previousOld and SessionMapState.NewFamiliarTrait == previousNew and SessionMapState.StatLine == 'oldLine')
print('hades2_choice_reroll_runtime_ok')
'''
CASES['circe_foreign_preview_after_spend'] = CIRCE_SETUP + r'''
M.dispatch('reroll_choice', params)
local foreign = {}; SessionMapState.OldFamiliarTrait = foreign
finishAction('circe-preview')
assert(M.requests['circe-preview'].status == 'outcome_unknown' and SessionMapState.OldFamiliarTrait == foreign and SessionMapState.NewFamiliarTrait == previousNew)
print('hades2_choice_reroll_runtime_ok')
'''
CASES['callback_lease_replaced'] = HARNESS.split('local observed =')[0] + r'''
local observed = M.dispatch('status', { includeCatalogs = false }).choiceReroll
M.dispatch('reroll_choice', { requestId = 'foreign-lease', menuToken = observed.menuToken, expectedCost = 1, includeCatalogs = false })
local callbackName
for name in pairs(_G) do if type(name) == 'string' and name:find('MacGamingTrainerChoiceReroll_', 1, true) == 1 then callbackName = name end end
local foreign = function() end; _G[callbackName] = foreign
finish()
assert(M.dispatch('status', { includeCatalogs = false }).lastAction.outcome == 'outcome_unknown')
assert(_G[callbackName] == foreign and source.UpgradeOptions[1].ItemName == 'CostumeA' and not inputBlocked and not ScreenState.InTransition)
print('hades2_choice_reroll_runtime_ok')
'''
CASES['unknown_carry_after_revision_cleanup'] = HARNESS + r'''
M.revision = 77
-- A terminal status does not reconcile a pending counter lock.
M.rerollsLock = 50
local value = CurrentRun.NumRerolls
M.dispatch('status', { includeCatalogs = false }); assert(CurrentRun.NumRerolls == value)
dofile(arg[1]); M = __MacGamingTrainerV1
assert(M.revision == 78 and M.terminalActionUnknown and M.dispatch('status', { includeCatalogs = false }).lastAction.outcome == 'outcome_unknown')
local ok, errorText = pcall(M.dispatch, 'set_rerolls', { requestId = 'new-revision-mutation', amount = 50 })
assert(not ok and tostring(errorText):find('MGT_OUTCOME_UNKNOWN', 1, true))
'''


for change_name, change in {'trait_tray': 'screen.TraitTrayOpened = true', 'nested_modal': "ActiveScreens.OtherNativeModal = { Name = 'OtherNativeModal' }", 'close_started': 'screen.Closing = true; screen.KeepOpen = false'}.items():
 for phase in ('before', 'after'):
    setup = r'''
local observed = M.dispatch('status', { includeCatalogs = false }).choiceReroll
local params = { requestId = 'nested-screen', menuToken = observed.menuToken, expectedCost = 1, includeCatalogs = false }
'''
    body = (change + "\nlocal ok = pcall(M.dispatch, 'reroll_choice', params); assert(not ok and CurrentRun.NumRerolls == 10, 'nested native modal accepted hidden parent choice')"
        if phase == 'before' else "M.dispatch('reroll_choice', params)\n" + change + r'''
finish()
assert(M.requests['nested-screen'].status == 'outcome_unknown' and source.UpgradeOptions[1].ItemName == 'CostumeA', 'nested modal allowed stale parent commit')
''')
    CASES[f'{change_name}_{phase}_spend'] = HARNESS.split('local observed =')[0] + setup + body + "\nprint('hades2_choice_reroll_runtime_ok')"
CASES['missing_native_icon'] = HARNESS.split('local observed =')[0] + r'''
local observed = M.dispatch('status', { includeCatalogs = false }).choiceReroll
screen.Components.RerollIcon = nil
local ok = pcall(M.dispatch, 'reroll_choice', { requestId = 'missing-icon', menuToken = observed.menuToken, expectedCost = 1, includeCatalogs = false })
assert(not ok and CurrentRun.NumRerolls == 10, 'known missing component spent before rejection')
print('hades2_choice_reroll_runtime_ok')
'''


CASES['before_coroutine_start_known_failure'] = HARNESS.split('local observed =')[0] + r'''
thread = function(fn) table.insert(pending, coroutine.create(fn)) end
local observed = M.dispatch('status', { includeCatalogs = false }).choiceReroll
M.dispatch('reroll_choice', { requestId = 'delayed-start', menuToken = observed.menuToken, expectedCost = 1, includeCatalogs = false })
source.UpgradeOptions = copy(source.UpgradeOptions)
finish()
assert(M.requests['delayed-start'].status == 'failed' and not M.terminalActionUnknown and CurrentRun.NumRerolls == 10)
print('hades2_choice_reroll_runtime_ok')
'''
CASES['locked_count_native_cost_history'] = HARNESS.split('local observed =')[0] + r'''
M.dispatch('lock_rerolls', { locked = true, includeCatalogs = false })
local observed = M.dispatch('status', { includeCatalogs = false }).choiceReroll
M.dispatch('reroll_choice', { requestId = 'locked-reroll', menuToken = observed.menuToken, expectedCost = 1, includeCatalogs = false })
finish()
assert(M.requests['locked-reroll'].status == 'completed' and CurrentRun.NumRerolls == 10 and M.rerollsLock == 10)
assert(CurrentRun.CurrentRoom.SpentRerolls[42] == 1 and M.dispatch('status', { includeCatalogs = false }).choiceReroll.cost == 2)
print('hades2_choice_reroll_runtime_ok')
'''
CASES['changed_cost_and_request_reuse'] = HARNESS.split('local observed =')[0] + r'''
local observed = M.dispatch('status', { includeCatalogs = false }).choiceReroll
CurrentRun.CurrentRoom.SpentRerolls = { [42] = 1 }
local ok, errorText = pcall(M.dispatch, 'reroll_choice', { requestId = 'wrong-cost', menuToken = observed.menuToken, expectedCost = 1, includeCatalogs = false })
assert(not ok and tostring(errorText):find('Choice reroll cost is stale', 1, true) and CurrentRun.NumRerolls == 10)
CurrentRun.CurrentRoom.SpentRerolls[42] = 0
M.dispatch('reroll_choice', { requestId = 'same-id', menuToken = observed.menuToken, expectedCost = 1, includeCatalogs = false })
finish()
ok, errorText = pcall(M.dispatch, 'reroll_choice', { requestId = 'same-id', menuToken = observed.menuToken, expectedCost = 2, includeCatalogs = false })
assert(not ok and tostring(errorText):find('requestId reused for a different action', 1, true) and CurrentRun.NumRerolls == 9)
print('hades2_choice_reroll_runtime_ok')
'''
CASES['same_pool_known_failure'] = HARNESS.split('local observed =')[0] + r'''
PresetEventArgs.ArachneCostumeChoices.UpgradeOptions = { copy(source.UpgradeOptions[1]), copy(source.UpgradeOptions[2]), copy(source.UpgradeOptions[3]) }
local observed = M.dispatch('status', { includeCatalogs = false }).choiceReroll
local ok, errorText = pcall(M.dispatch, 'reroll_choice', { requestId = 'no-new-pool', menuToken = observed.menuToken, expectedCost = 1, includeCatalogs = false })
assert(not ok and tostring(errorText):find('Choice reroll pool has no changed eligible candidates', 1, true) and CurrentRun.NumRerolls == 10 and not M.requests['no-new-pool'])
print('hades2_choice_reroll_runtime_ok')
'''
CASES['unsupported_source_known_failure'] = HARNESS.split('local observed =')[0] + r'''
for _, name in ipairs({ 'SpellDrop', 'NemesisTrade', 'UnknownNPC', 'TalentDrop' }) do
  source.Name = name
  local observed = M.dispatch('status', { includeCatalogs = false }).choiceReroll
  assert(not observed.available and observed.reason == 'hades2.reroll.unsupported')
  local ok = pcall(M.dispatch, 'reroll_choice', { requestId = name, menuToken = 'old', expectedCost = 1, includeCatalogs = false })
  assert(not ok and CurrentRun.NumRerolls == 10)
end
print('hades2_choice_reroll_runtime_ok')
'''
CASES['synthetic_fixed_native_requirement_owner'] = prefix + r'''
EnemyData.NPC_Medea_01 = { Name = 'NPC_Medea_01' }
for _, option in ipairs(pool) do option.GameStateRequirements = { enabled = true } end
PresetEventArgs.MedeaCurseChoices = { UpgradeOptions = pool }
IsGameStateEligible = function(value, requirements) assert(value.Name == 'NPC_Medea_01', 'fixed synthetic source lost native eligibility identity'); return requirements.enabled end
M.dispatch('open_special_choice', { requestId = 'native-name-open', source = 'Medea', includeCatalogs = false })
rerollAndSelect('native-name-reroll')
print('hades2_choice_reroll_runtime_ok')
'''
CASES['synthetic_menus_have_separate_cost_history'] = prefix + r'''
EnemyData.NPC_Medea_01 = { Name = 'NPC_Medea_01' }; PresetEventArgs.MedeaCurseChoices = { UpgradeOptions = pool }
M.dispatch('open_special_choice', { requestId = 'menu-one', source = 'Medea', includeCatalogs = false })
rerollAndSelect('menu-one-reroll')
CurrentRun.NumRerolls = 10
M.dispatch('open_special_choice', { requestId = 'menu-two', source = 'Medea', includeCatalogs = false })
assert(M.dispatch('status', { includeCatalogs = false }).choiceReroll.cost == 1)
rerollAndSelect('menu-two-reroll')
print('hades2_choice_reroll_runtime_ok')
'''


CASES['only_new_candidate_blocked'] = HARNESS.split('local observed =')[0] + r'''
local observed = M.dispatch('status', { includeCatalogs = false }).choiceReroll
local originalCreate = CreateBoonLootButtons
CreateBoonLootButtons = function(s, value)
  for _, option in ipairs(value.UpgradeOptions) do if option.ItemName == 'CostumeD' then option.Blocked = true end end
  originalCreate(s, value)
end
M.dispatch('reroll_choice', { requestId = 'blocked-new-candidate', menuToken = observed.menuToken, expectedCost = 1, includeCatalogs = false })
finish()
assert(M.requests['blocked-new-candidate'].status == 'outcome_unknown', 'only changed candidate was blocked but reroll claimed completion')
assert(not inputBlocked and not ScreenState.InTransition)
print('hades2_choice_reroll_runtime_ok')
'''


GUARD_UNKNOWN = HARNESS.split('local observed =')[0] + r'''
M.dispatch('lock_rerolls', { locked = true, includeCatalogs = false })
PostRerollPanelPresentation = function() error('post-spend presentation fault') end
local observed = M.dispatch('status', { includeCatalogs = false }).choiceReroll
M.dispatch('reroll_choice', { requestId = 'guard-unknown', menuToken = observed.menuToken, expectedCost = 1, includeCatalogs = false })
finish()
assert(M.terminalActionUnknown and M.requests['guard-unknown'].status == 'outcome_unknown' and UpdateTimers == M.guardWrapper)
'''
CASES['unknown_timer_does_not_reinstall_foreign_hook'] = GUARD_UNKNOWN + r'''
local foreignCalls = 0
local foreign = function() foreignCalls = foreignCalls + 1 end
UpdateRerollUI = foreign
CurrentRun.NumRerolls = 0
UpdateTimers(0.016)
assert(UpdateRerollUI == foreign and foreignCalls == 0 and CurrentRun.NumRerolls == 0, 'unknown timer adopted a foreign hook')
print('hades2_choice_reroll_runtime_ok')
'''
CASES['unknown_timer_does_not_adopt_or_enforce_new_owner'] = GUARD_UNKNOWN + r'''
local previousRun, previousHero, previousSession = M.run, M.hero, M.session
CurrentRun = copy(CurrentRun); CurrentRun.NumRerolls = 0
UpdateTimers(0.016)
M.enforceLocksInternal()
assert(CurrentRun.NumRerolls == 0 and M.run == previousRun and M.hero == previousHero and M.session == previousSession, 'unknown timer replayed into a new run owner')
print('hades2_choice_reroll_runtime_ok')
'''
CASES['unknown_keeps_owned_current_run_lock'] = GUARD_UNKNOWN + r'''
local previousUI = UpdateRerollUI
CurrentRun.NumRerolls = 0
UpdateTimers(0.016)
assert(CurrentRun.NumRerolls == 10 and UpdateRerollUI == previousUI and M.rerollsLock == 10, 'uncertain one-shot disabled an already owned current-run durable hook')
print('hades2_choice_reroll_runtime_ok')
'''

CASES['echo_native_ban_after_spend'] = prefix + r'''
-- Supported RunLogic.IsTraitEligible's ban rule, reached through the native
-- eligibility API rather than through a Trainer snapshot of BannedTraits.
IsTraitEligible = function(data, args)
  return data ~= nil and not data.Ineligible and (not CurrentRun.BannedTraits[data.Name] or (args and args.AllowBannedTraits))
end
GameState.RunHistory = { { TraitRarityCache = { ChoiceA = 'Common', ChoiceB = 'Rare', ChoiceC = 'Epic', ChoiceD = 'Rare' } } }
show({ Name = 'NPC_Echo_01', ObjectId = -1, MenuTitle = 'EchoChoiceMenu_LastRun', OnPressedFunctionNameOverride = 'SelectEchoBoon',
  UpgradeOptions = { copy(pool[1]), copy(pool[2]), copy(pool[3]) } })
local observed = M.dispatch('status', { includeCatalogs = false }).choiceReroll
M.dispatch('reroll_choice', { requestId = 'native-ban', menuToken = observed.menuToken, expectedCost = 1, includeCatalogs = false })
CurrentRun.BannedTraits.ChoiceD = true
assert(not IsTraitEligible(TraitData.ChoiceD))
finishAction('native-ban')
finish()
assert(M.requests['native-ban'].status == 'outcome_unknown' and source.UpgradeOptions[1].ItemName == 'ChoiceA', 'callback committed a newly native-ineligible Echo candidate')
assert(not inputBlocked and not ScreenState.InTransition)
print('hades2_choice_reroll_runtime_ok')
'''

for context, change in {
 'closing': 'screen.Closing = true; screen.KeepOpen = false',
 'nested': 'screen.TraitTrayOpened = true; ActiveScreens.TraitTray = {}',
}.items():
 CASES[f'{context}_post_failure_unwinds_owned_input'] = HARNESS.split('local observed =')[0] + r'''
PostRerollPanelPresentation = function() error('native post-presentation fault') end
local observed = M.dispatch('status', { includeCatalogs = false }).choiceReroll
M.dispatch('reroll_choice', { requestId = 'owned-unwind', menuToken = observed.menuToken, expectedCost = 1, includeCatalogs = false })
''' + change + r'''
finish()
assert(M.requests['owned-unwind'].status == 'outcome_unknown' and source.UpgradeOptions[1].ItemName == 'CostumeA')
assert(not inputBlocked and not ScreenState.InTransition, 'exception cleanup skipped the lease-owned input block after its menu became non-actionable')
print('hades2_choice_reroll_runtime_ok')
'''

for owner, change in {
 'session': 'SessionState = {}',
 'run': 'CurrentRun = copy(CurrentRun)',
 'screen': 'local foreign = copy(screen); ScreenAnchors.ChoiceScreen = foreign; ActiveScreens.UpgradeChoice = foreign',
 'screen_state': 'ScreenState = { InTransition = true }',
}.items():
 CASES[f'post_failure_preserves_foreign_{owner}'] = HARNESS.split('local observed =')[0] + r'''
PostRerollPanelPresentation = function() error('native post-presentation fault') end
local observed = M.dispatch('status', { includeCatalogs = false }).choiceReroll
M.dispatch('reroll_choice', { requestId = 'foreign-unwind', menuToken = observed.menuToken, expectedCost = 1, includeCatalogs = false })
local originalState = ScreenState
''' + change + r'''
finish()
assert(M.requests['foreign-unwind'].status == 'outcome_unknown')
assert(inputBlocked and originalState.InTransition and ScreenState.InTransition, 'exception unwind cleared input/transition belonging to a foreign owner')
print('hades2_choice_reroll_runtime_ok')
'''

for family, changed_name in {'ZeusUpgrade': 'ChoiceD', 'TrialUpgrade': 'CurseB'}.items():
 CASES[f'{family}_native_ban_after_spend'] = prefix + f"expectedNativeName = '{family}'\n" + r'''
LootData[expectedNativeName] = { GodLoot = true }
local value = { Name = expectedNativeName, ObjectId = 42, Traits = { 'ChoiceA', 'ChoiceB', 'ChoiceC', 'ChoiceD', 'ChoiceE' },
  UpgradeOptions = { copy(pool[1]), copy(pool[2]), copy(pool[3]) } }
if expectedNativeName == 'TrialUpgrade' then
  value.TransformingTraits = true; value.PermanentTraits = value.Traits; value.TemporaryTraits = { 'CurseB' }
  TraitData.CurseB = { Name = 'CurseB' }; CurrentRun.Hero.TraitDictionary.ChoiceD = { Name = 'ChoiceD' }
  for _, option in ipairs(pool) do option.Type = 'TransformingTrait'; option.SecondaryItemName = 'CurseB' end
  value.UpgradeOptions = { copy(pool[1]), copy(pool[2]), copy(pool[3]) }
end
show(value)
local observed = M.dispatch('status', { includeCatalogs = false }).choiceReroll
M.dispatch('reroll_choice', { requestId = 'live-native-ban', menuToken = observed.menuToken, expectedCost = 1, includeCatalogs = false })
''' + f"CurrentRun.BannedTraits.{changed_name} = true\n" + r'''
finish()
assert(M.requests['live-native-ban'].status == 'outcome_unknown' and source.UpgradeOptions[1].ItemName == 'ChoiceA', 'callback ignored live native family eligibility')
assert(not inputBlocked and not ScreenState.InTransition)
print('hades2_choice_reroll_runtime_ok')
'''

CASES['native_ban_before_coroutine_spends_nothing'] = CASES['ZeusUpgrade_native_ban_after_spend'].replace(
    "M.dispatch('reroll_choice', { requestId = 'live-native-ban'",
    "thread = function(fn) table.insert(pending, coroutine.create(fn)) end\nM.dispatch('reroll_choice', { requestId = 'live-native-ban'",
).replace("status == 'outcome_unknown'", "status == 'failed'").replace(
    "assert(not inputBlocked and not ScreenState.InTransition)",
    "assert(CurrentRun.NumRerolls == 10 and not M.terminalActionUnknown and not inputBlocked and not ScreenState.InTransition)",
)

for case, code in CASES.items():
 with tempfile.TemporaryDirectory(prefix='mgt-choice-reroll-') as temporary:
    harness = Path(temporary) / (case + '.lua')
    harness.write_text(code)
    result = subprocess.run([LUA, str(harness), str(ROOT / 'Backend/games/hades2/runtime/hades.lua'),
                             str(RESIDENT_DISPATCH_CONTRACT)], cwd=ROOT, text=True,
                            capture_output=True, timeout=30)
    if result.returncode:
        print(result.stdout)
        print(result.stderr)
        raise SystemExit(result.returncode)
    assert 'hades2_choice_reroll_runtime_ok' in result.stdout
print('hades2_choice_reroll_ok')
