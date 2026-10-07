import subprocess
import tempfile
from pathlib import Path

from lua_runtime_support import RESIDENT_DISPATCH_CONTRACT, require_lua52

ROOT = Path(__file__).resolve().parents[1]
LUA = require_lua52("Force Enable Rerolls Nemesis trade behavior")

SOURCE = (ROOT / "tests/test_hades2_force_enable_rerolls.py").read_text()
START = SOURCE.index("HARNESS = r'''") + len("HARNESS = r'''")
END = SOURCE.index("\n'''\n\nwith tempfile", START)
BASE_HARNESS = SOURCE[START:END]

NEMESIS_CASES = r'''
-- Nemesis trade choices are transaction owners rather than UpgradeChoice loot.
-- A forced reroll must keep the native TradeScreen and eventual TradeDoExchange
-- bound to the same copied offer instead of changing presentation only.
M.dispatch('set_feature', { feature = 'forceEnableRerolls', value = false, includeCatalogs = false })

local nextTradeComponentId = 900
local function tradeComponent()
  nextTradeComponentId = nextTradeComponentId + 1
  return { Id = nextTradeComponentId, Visible = false }
end

ScreenData.UpgradeChoice = {
  ComponentData = {
    RerollIcon = { Animation = 'RerollIcon', Alpha = 0 },
    ActionBar = {
      Children = {
        RerollButton = {
          Graphic = 'ContextualActionButton',
          Alpha = 0,
          Data = {
            OnPressedFunctionName = 'AttemptPanelReroll',
            ControlHotkeys = { 'Reroll' },
          },
          Text = ' ',
          AltText = 'Boon_Reroll',
        },
      },
    },
  },
}
ScreenData.TradeScreen = {
  ComponentData = {
    ActionBar = {
      ChildrenOrder = { 'AcceptButton', 'CloseButton' },
      Children = { AcceptButton = {}, CloseButton = {} },
    },
  },
}

CreateComponentFromData = function(screenData, data)
  local value = tradeComponent()
  value.Data = data
  return value
end
Attach = function() end
GetDisplayName = function(args) return args.Text or '' end
ApproximateStringWidth = function(text) return #tostring(text or '') end
UIData = {
  ContextualButtonSpacing = 100,
  AutoAlignContextualButtonGlyphWidth = 0,
  AutoAlignContextualButtonMinWidth = 40,
  AutoAlignContextualButtonSpacing = 10,
}
Destroy = function() end
local panelSpendMutations = 0
local rerollUiHook = nil
IncrementTableValue = function(values, key, amount)
  panelSpendMutations = panelSpendMutations + 1
  values[key] = (values[key] or 0) + amount
end
UpdateRerollUI = function(value)
  if rerollUiHook ~= nil then rerollUiHook(value) end
end

local function mountTradeScreenComponents(screen)
  local root = ScreenData.TradeScreen.ComponentData
  screen.Components.ActionBar = {
    Id = tradeComponent().Id,
    AutoAlignContextualButtons = true,
    AutoAlignJustification = 'Right',
  }
  screen.Components.AcceptButton = tradeComponent()
  screen.Components.CloseButton = tradeComponent()
  if root.RerollIcon then screen.Components.RerollIcon = tradeComponent() end
  if root.ActionBar and root.ActionBar.Children
      and root.ActionBar.Children.RerollButton then
    screen.Components.RerollButton = tradeComponent()
  end
end

RandomInt = function(minimum) return minimum end
IsGameStateEligible = function(_, _, requirements)
  return not (type(requirements) == 'table' and requirements.Blocked)
end
local randomChoiceCalls = 0
GetRandomValue = function(values)
  randomChoiceCalls = randomChoiceCalls + 1
  if randomChoiceCalls == 4 and #values > 1 then return values[2] end
  return values[1]
end
HasResource = function(name, amount)
  return (GameState.Resources[name] or 0) >= amount
end
SpendResource = function(name, amount)
  GameState.Resources[name] = (GameState.Resources[name] or 0) - amount
end

ConsumableData.TradeRewardA = { Name = 'TradeRewardA' }
ConsumableData.TradeRewardB = { Name = 'TradeRewardB' }
ConsumableData.TradeRewardC = { Name = 'TradeRewardC' }
ConsumableData.DamageRewardA = { Name = 'DamageRewardA' }
ConsumableData.DamageRewardB = { Name = 'DamageRewardB' }
ConsumableData.DamageRewardBlocked = { Name = 'DamageRewardBlocked' }
ConsumableData.TraitRewardA = { Name = 'TraitRewardA' }
ConsumableData.TraitRewardB = { Name = 'TraitRewardB' }
ConsumableData.TraitRewardBlocked = { Name = 'TraitRewardBlocked' }

PresetEventArgs.NemesisBuyItemChoices = {
  GiveOptions = {
    { UseGetCost = true },
  },
  GetOptions = {
    { Name = 'TradeRewardA', CostResourceName = 'Money', CostResourceMin = 11, CostResourceMax = 11 },
    { Name = 'TradeRewardB', CostResourceName = 'Money', CostResourceMin = 17, CostResourceMax = 17 },
    { Name = 'TradeRewardC', CostResourceName = 'Money', CostResourceMin = 23, CostResourceMax = 23 },
  },
}
PresetEventArgs.NemesisTakeDamageForItemChoices = {
  GiveOptions = {
    { UseGetDamage = true },
  },
  GetOptions = {
    { Name = 'DamageRewardA', DamageAmountMin = 7, DamageAmountMax = 7 },
    { Name = 'DamageRewardB', DamageAmountMin = 13, DamageAmountMax = 13 },
    { Name = 'DamageRewardBlocked', DamageAmountMin = 99, DamageAmountMax = 99,
      GameStateRequirements = { Blocked = true } },
  },
}
PresetEventArgs.NemesisGiveTraitForItemChoices = {
  GiveOptions = {
    { SellTrait = true },
  },
  GetOptions = {
    { Name = 'TraitRewardA' },
    { Name = 'TraitRewardB' },
    { Name = 'TraitRewardBlocked', GameStateRequirements = { Blocked = true } },
  },
}

local tradeOpenCount = 0
local tradeMode = 'money'
local displayedReward
local displayedCost
local displayedDamage
local displayedSale
local settledReward
local settledCost
local settledDamage
local settledSale
local removedTrait
local sellGenerationCount = 0
local sellSequence = { 'SellBoonA', 'SellBoonB', 'SellBoonC' }
local observedCosts = {}

GenerateSellTraitShop = function()
  sellGenerationCount = sellGenerationCount + 1
  local name = sellSequence[math.min(sellGenerationCount, #sellSequence)]
  CurrentRun.CurrentRoom.SellOptions = { { Name = name } }
end
RemoveWeaponTrait = function(name)
  removedTrait = name
end
Damage = function(hero, args)
  hero.Health = hero.Health - args.DamageAmount
  settledDamage = args.DamageAmount
end

local function resetTrade(mode, rerolls)
  tradeMode = mode
  tradeOpenCount = 0
  randomChoiceCalls = 0
  panelSpendMutations = 0
  rerollUiHook = nil
  displayedReward = nil
  displayedCost = nil
  displayedDamage = nil
  displayedSale = nil
  settledReward = nil
  settledCost = nil
  settledDamage = nil
  settledSale = nil
  removedTrait = nil
  sellGenerationCount = 0
  observedCosts = {}
  CurrentRun.NumRerolls = rerolls or 5
  CurrentRun.CurrentRoom.SpentRerolls = {}
  CurrentRun.CurrentRoom.SellOptions = nil
  CurrentRun.Hero.Health = 100
end

CloseTradeScreen = function(screen)
  if tradeMode == 'closeFailure' and tradeOpenCount == 1 then
    error('simulated TradeScreen close failure after native spend')
  end
  screen.KeepOpen = false
  if ActiveScreens.TradeScreen == screen then ActiveScreens.TradeScreen = nil end
end

HandleScreenInput = function(screen)
  assert(screen.Name == 'TradeScreen')
  if tradeMode == 'closeFailure' then
    local button = screen.Components.RerollButton
    assert(type(button) == 'table' and button.Visible,
      'close-failure setup did not expose the Nemesis reroll control'
        .. ' button=' .. tostring(button)
        .. ' visible=' .. tostring(type(button) == 'table' and button.Visible)
        .. ' cost=' .. tostring(type(button) == 'table' and button.Cost)
        .. ' onPressed=' .. tostring(type(button) == 'table' and button.OnPressedFunctionName)
        .. ' rerollFn=' .. tostring(type(button) == 'table' and button.RerollFunctionName)
        .. ' rerolls=' .. tostring(CurrentRun and CurrentRun.NumRerolls)
        .. ' spent=' .. tostring(CurrentRun and CurrentRun.CurrentRoom
          and CurrentRun.CurrentRoom.SpentRerolls
          and CurrentRun.CurrentRoom.SpentRerolls[screen.Source.ObjectId])
        .. ' desired=' .. tostring(M.desiredFeatures.forceEnableRerolls)
        .. ' terminal=' .. tostring(M.terminalActionUnknown))
    CallFunctionName(button.OnPressedFunctionName, screen, button)
    assert(panelSpendMutations == 1 and CurrentRun.NumRerolls == 4
      and CurrentRun.CurrentRoom.SpentRerolls[screen.Source.ObjectId] == 1,
      'close-failure Nemesis reroll did not preserve the completed native spend')
    assert(screen.KeepOpen,
      'failed close unexpectedly consumed the native TradeScreen')
    local mutationOk, mutationError = pcall(M.dispatch, 'set_rerolls', {
      value = 3, includeCatalogs = false,
    })
    assert(not mutationOk
      and string.find(tostring(mutationError), 'MGT_OUTCOME_UNKNOWN', 1, true) ~= nil,
      'post-spend TradeScreen failure did not close the resident mutation boundary')
    assert(not button.Visible,
      'outcome-unknown TradeScreen left a second Nemesis reroll spend available')
    assert(M.featureErrors.forceEnableRerolls == 'hades2.error.outcomeUnknownRuntime',
      'terminal Nemesis feature error bypassed bilingual presentation')
    M.dispatch('disable_all', { includeCatalogs = false })
    return
  end
  if tradeMode == 'postSpendStale' then
    local button = screen.Components.RerollButton
    assert(type(button) == 'table' and button.Visible,
      'post-spend stale setup did not expose the Nemesis reroll control')
    local ownerRun = CurrentRun
    local replacementRun = {
      Hero = ownerRun.Hero,
      CurrentRoom = {},
      NumRerolls = 11,
      PickedTraits = {},
      BannedTraits = {},
    }
    rerollUiHook = function()
      rerollUiHook = nil
      CurrentRun = replacementRun
    end
    CallFunctionName(button.OnPressedFunctionName, screen, button)
    assert(panelSpendMutations == 1 and ownerRun.NumRerolls == 4
      and ownerRun.CurrentRoom.SpentRerolls[screen.Source.ObjectId] == 1,
      'post-spend stale Nemesis reroll did not preserve the already-completed native spend')
    assert(replacementRun.NumRerolls == 11
      and replacementRun.CurrentRoom.SpentRerolls == nil,
      'post-spend stale Nemesis reroll mutated the replacement run')
    local mutationOk, mutationError = pcall(M.dispatch, 'set_rerolls', {
      value = 3, includeCatalogs = false,
    })
    assert(not mutationOk
      and string.find(tostring(mutationError), 'MGT_OUTCOME_UNKNOWN', 1, true) ~= nil,
      'post-spend stale Nemesis reroll did not close the resident mutation boundary')
    assert(not button.Visible,
      'post-spend stale outcome left a second Nemesis reroll spend available')
    assert(M.featureErrors.forceEnableRerolls == 'hades2.error.outcomeUnknownRuntime',
      'post-spend stale feature error bypassed bilingual presentation')
    assert(screen.KeepOpen,
      'post-spend stale Nemesis reroll replayed or closed the uncertain transaction automatically')
    M.dispatch('disable_all', { includeCatalogs = false })
    CurrentRun = ownerRun
    CloseTradeScreen(screen)
    return
  end
  if tradeMode == 'staleMenu' then
    local button = screen.Components.RerollButton
    assert(type(button) == 'table' and button.Visible,
      'stale-menu setup did not expose the Nemesis reroll control')
    screen.KeepOpen = false
    CallFunctionName(button.OnPressedFunctionName, screen, button)
    assert(panelSpendMutations == 0 and CurrentRun.NumRerolls == 5,
      'closed Nemesis TradeScreen entered native reroll spend')
    return
  end
  if tradeMode == 'staleSource' then
    local button = screen.Components.RerollButton
    assert(type(button) == 'table' and button.Visible,
      'stale-source setup did not expose the Nemesis reroll control')
    screen.Source = { Name = 'NPC_Nemesis_01', ObjectId = 9999, Accepted = false }
    CallFunctionName(button.OnPressedFunctionName, screen, button)
    assert(panelSpendMutations == 0 and CurrentRun.NumRerolls == 5,
      'changed Nemesis TradeScreen source entered native reroll spend')
    return
  end
  if tradeMode == 'staleRun' then
    local button = screen.Components.RerollButton
    assert(type(button) == 'table' and button.Visible,
      'stale-run setup did not expose the Nemesis reroll control')
    local ownerRun = CurrentRun
    local replacementRun = {
      Hero = ownerRun.Hero,
      CurrentRoom = {},
      NumRerolls = 7,
      PickedTraits = {},
      BannedTraits = {},
    }
    CurrentRun = replacementRun
    CallFunctionName(button.OnPressedFunctionName, screen, button)
    assert(panelSpendMutations == 0,
      'stale Nemesis TradeScreen entered native reroll spend before refusing')
    assert(replacementRun.NumRerolls == 7
      and (replacementRun.CurrentRoom.SpentRerolls == nil
        or replacementRun.CurrentRoom.SpentRerolls[screen.Source.ObjectId] == nil),
      'stale Nemesis TradeScreen mutated the replacement run')
    CurrentRun = ownerRun
    CloseTradeScreen(screen)
    return
  end
  if tradeMode == 'exhausted' then
    local button = screen.Components.RerollButton
    assert(type(button) == 'table' and not button.Visible,
      'exhausted Nemesis trade exposed a spendable reroll')
    CloseTradeScreen(screen)
    return
  end

  local rerollsWanted = tradeMode == 'twoRerolls' and 2 or 1
  if tradeOpenCount <= rerollsWanted then
    local button = screen.Components.RerollButton
    assert(type(button) == 'table' and button.Visible
      and button.OnPressedFunctionName == 'AttemptPanelReroll',
      'Nemesis TradeScreen did not expose the native-style forced reroll action')
    local expectedBefore = tradeOpenCount * 2
    assert(randomChoiceCalls == expectedBefore,
      'opening a Nemesis trade consumed RNG beyond native give/get selection')
    observedCosts[#observedCosts + 1] = button.Cost
    local before = screen.ChosenGetOption.Name
    CallFunctionName(button.OnPressedFunctionName, screen, button)
    assert(randomChoiceCalls == expectedBefore + 2,
      'Nemesis trade reroll did not regenerate through native-shaped give/get draws')
    assert(not screen.KeepOpen, 'Nemesis trade reroll did not close the old native screen before redraw')
    assert(screen.ChosenGetOption.Name == before,
      'Nemesis trade reroll mutated the already-presented transaction plan in place')
    return
  end

  displayedReward = screen.ChosenGetOption.Name
  displayedCost = screen.ChosenGiveOption.Cost
  displayedDamage = screen.ChosenGiveOption.DamageAmount
  displayedSale = type(CurrentRun.CurrentRoom.SellOptions) == 'table'
    and CurrentRun.CurrentRoom.SellOptions[1]
    and CurrentRun.CurrentRoom.SellOptions[1].Name or nil
  if tradeMode == 'decline' then
    CloseTradeScreen(screen)
    return
  end
  screen.Source.Accepted = true
  CloseTradeScreen(screen)
end

OpenTradeScreen = function(source, args, chosenGiveOption, chosenGetOption)
  tradeOpenCount = tradeOpenCount + 1
  if tradeMode == 'initialFailure' then
    error('simulated initial TradeScreen failure before a reroll')
  end
  if tradeMode == 'redrawFailure' and tradeOpenCount == 2 then
    error('simulated replacement TradeScreen failure after completed reroll')
  end
  local screen = {
    Name = 'TradeScreen',
    Source = source,
    Args = args,
    ChosenGiveOption = chosenGiveOption,
    ChosenGetOption = chosenGetOption,
    Components = {},
    KeepOpen = true,
  }
  ActiveScreens.TradeScreen = screen
  mountTradeScreenComponents(screen)

  if chosenGiveOption.SellTrait then
    GenerateSellTraitShop(CurrentRun, CurrentRun.CurrentRoom, { SellOptionCount = 1 })
  elseif chosenGiveOption.UseGetCost then
    chosenGiveOption.Cost = RandomInt(
      chosenGetOption.CostResourceMin,
      chosenGetOption.CostResourceMax
    )
  elseif chosenGiveOption.UseGetDamage then
    chosenGiveOption.DamageAmount = RandomInt(
      chosenGetOption.DamageAmountMin,
      chosenGetOption.DamageAmountMax
    )
  end

  HandleScreenInput(screen)
  return screen
end

NemesisTradeChoice = function(source, args, dialogueScreen)
  local eligibleGiveOptions = {}
  for _, option in ipairs(args.GiveOptions or {}) do
    if option.GameStateRequirements == nil
        or IsGameStateEligible(CurrentRun, option, option.GameStateRequirements) then
      eligibleGiveOptions[#eligibleGiveOptions + 1] = option
    end
  end
  local eligibleGetOptions = {}
  for _, option in ipairs(args.GetOptions or {}) do
    if option.GameStateRequirements == nil
        or IsGameStateEligible(CurrentRun, option, option.GameStateRequirements) then
      eligibleGetOptions[#eligibleGetOptions + 1] = option
    end
  end
  local chosenGiveOption = GetRandomValue(eligibleGiveOptions)
  local chosenGetOption = GetRandomValue(eligibleGetOptions)
  OpenTradeScreen(source, args, chosenGiveOption, chosenGetOption)
  if source.Accepted then
    dialogueScreen.OnCloseFinishedFunctionName = 'TradeDoExchange'
    args.ChosenGiveOption = chosenGiveOption
    args.ChosenGetOption = chosenGetOption
    dialogueScreen.OnCloseFinishedFunctionArgs = args
  end
end

TradeDoExchange = function(screen, args)
  local giveOption = args.ChosenGiveOption
  local getOption = args.ChosenGetOption
  if giveOption.SellTrait then
    for _, sellData in pairs(CurrentRun.CurrentRoom.SellOptions or {}) do
      RemoveWeaponTrait(sellData.Name)
    end
    CurrentRun.CurrentRoom.SellOptions = {}
    settledSale = removedTrait
  end
  if giveOption.UseGetCost then
    SpendResource(getOption.CostResourceName, giveOption.Cost)
  end
  if giveOption.DamageAmount then
    Damage(CurrentRun.Hero, { DamageAmount = giveOption.DamageAmount, PureDamage = true })
  end
  settledReward = getOption.Name
  settledCost = giveOption.Cost
  settledDamage = giveOption.DamageAmount or settledDamage
end

GameState.Resources.Money = 100
resetTrade('money', 5)
local source = { Name = 'NPC_Nemesis_01', ObjectId = 801, Accepted = false }
local dialogue = {}

local enabled = M.dispatch('set_feature', {
  feature = 'forceEnableRerolls', value = true, includeCatalogs = false,
})
assert(enabled.activeFeatures.forceEnableRerolls,
  'Nemesis trade seam made Force Enable Rerolls unavailable')

NemesisTradeChoice(source, PresetEventArgs.NemesisBuyItemChoices, dialogue)
assert(tradeOpenCount == 2, 'one Nemesis trade reroll did not regenerate exactly one native screen')
assert(displayedReward ~= 'TradeRewardA'
  and (displayedReward == 'TradeRewardB' or displayedReward == 'TradeRewardC'),
  'Nemesis trade reroll did not produce a genuinely changed eligible reward')
assert(CurrentRun.NumRerolls == 4
  and CurrentRun.CurrentRoom.SpentRerolls[801] == 1,
  'Nemesis trade reroll did not spend exactly one Change of Fate through AttemptPanelReroll')
assert(dialogue.OnCloseFinishedFunctionName == 'TradeDoExchange'
  and type(dialogue.OnCloseFinishedFunctionArgs) == 'table',
  'accepted Nemesis trade lost its native deferred exchange lifecycle')

TradeDoExchange(dialogue, dialogue.OnCloseFinishedFunctionArgs)
assert(settledReward == displayedReward and settledCost == displayedCost,
  'Nemesis reroll displayed one transaction but settled a different plan')
assert(GameState.Resources.Money == 100 - displayedCost,
  'Nemesis money trade did not settle the final displayed copied plan exactly once')

local preset = PresetEventArgs.NemesisBuyItemChoices
assert(preset.GiveOptions[1].Cost == nil
  and preset.GetOptions[1].SpawnPoint == nil
  and preset.GetOptions[2].SpawnPoint == nil,
  'Nemesis force reroll mutated shared PresetEventArgs transaction pools')

-- Damage-for-item keeps the prepared damage amount on the same copied plan
-- that is displayed and later settled. Ineligible rewards never enter reroll.
resetTrade('damage', 5)
local damageSource = { Name = 'NPC_Nemesis_01', ObjectId = 804, Accepted = false }
local damageDialogue = {}
NemesisTradeChoice(damageSource, PresetEventArgs.NemesisTakeDamageForItemChoices, damageDialogue)
assert(displayedReward == 'DamageRewardB' and displayedDamage == 13,
  'Nemesis damage reroll did not present the changed eligible native offer')
TradeDoExchange(damageDialogue, damageDialogue.OnCloseFinishedFunctionArgs)
assert(settledReward == displayedReward and settledDamage == displayedDamage
  and CurrentRun.Hero.Health == 100 - displayedDamage,
  'Nemesis damage trade settled different damage/reward than displayed')
assert(PresetEventArgs.NemesisTakeDamageForItemChoices.GiveOptions[1].DamageAmount == nil,
  'Nemesis damage reroll mutated the shared preset give option')

-- Trait-sale trades may regenerate both the reward and the native one-trait
-- SellOptions owner. The final displayed sale is the one native exchange removes.
resetTrade('traitSale', 5)
local traitSource = { Name = 'NPC_Nemesis_01', ObjectId = 805, Accepted = false }
local traitDialogue = {}
NemesisTradeChoice(traitSource, PresetEventArgs.NemesisGiveTraitForItemChoices, traitDialogue)
assert(displayedReward == 'TraitRewardB' and displayedSale == 'SellBoonB',
  'Nemesis trait-sale reroll did not present the changed native reward/sale')
TradeDoExchange(traitDialogue, traitDialogue.OnCloseFinishedFunctionArgs)
assert(settledReward == displayedReward and settledSale == displayedSale
  and removedTrait == displayedSale,
  'Nemesis trait-sale exchange removed a trait different from the displayed sale')

-- Declining after a deliberate reroll spends only that reroll; it never schedules
-- or performs the trade exchange.
resetTrade('decline', 5)
GameState.Resources.Money = 100
local declineSource = { Name = 'NPC_Nemesis_01', ObjectId = 806, Accepted = false }
local declineDialogue = {}
NemesisTradeChoice(declineSource, PresetEventArgs.NemesisBuyItemChoices, declineDialogue)
assert(declineDialogue.OnCloseFinishedFunctionName == nil
  and GameState.Resources.Money == 100
  and CurrentRun.NumRerolls == 4
  and settledReward == nil,
  'declined Nemesis reroll performed or scheduled an exchange')

-- A structurally exhausted pool keeps the injected Hades control unavailable and
-- spends nothing.
local fullMoneyPool = PresetEventArgs.NemesisBuyItemChoices.GetOptions
PresetEventArgs.NemesisBuyItemChoices.GetOptions = { fullMoneyPool[1] }
resetTrade('exhausted', 5)
local exhaustedSource = { Name = 'NPC_Nemesis_01', ObjectId = 807, Accepted = false }
NemesisTradeChoice(exhaustedSource, PresetEventArgs.NemesisBuyItemChoices, {})
assert(CurrentRun.NumRerolls == 5 and panelSpendMutations == 0,
  'exhausted Nemesis trade spent a reroll')
PresetEventArgs.NemesisBuyItemChoices.GetOptions = fullMoneyPool

-- Repeated native clicks use the same Boon panel base/escalation policy.
resetTrade('twoRerolls', 5)
local repeatedSource = { Name = 'NPC_Nemesis_01', ObjectId = 808, Accepted = false }
local repeatedDialogue = {}
NemesisTradeChoice(repeatedSource, PresetEventArgs.NemesisBuyItemChoices, repeatedDialogue)
assert(observedCosts[1] == 1 and observedCosts[2] == 2
  and CurrentRun.NumRerolls == 2
  and CurrentRun.CurrentRoom.SpentRerolls[808] == 2,
  'Nemesis repeated rerolls did not preserve native escalating panel cost')

-- Existing reroll-count lock remains independent: native spend/history occurs,
-- then UpdateRerollUI reconciles the count to the locked value.
resetTrade('money', 5)
M.dispatch('lock_rerolls', { requestId = 'nemesis-lock', locked = true, includeCatalogs = false })
local lockedSource = { Name = 'NPC_Nemesis_01', ObjectId = 809, Accepted = false }
NemesisTradeChoice(lockedSource, PresetEventArgs.NemesisBuyItemChoices, {})
assert(CurrentRun.NumRerolls == 5
  and CurrentRun.CurrentRoom.SpentRerolls[809] == 1,
  'Nemesis reroll broke independent reroll-count lock semantics')
M.dispatch('lock_rerolls', { requestId = 'nemesis-unlock', locked = false, includeCatalogs = false })

-- Closed/replaced native owners are deterministic pre-spend refusals.
resetTrade('staleMenu', 5)
local staleMenuSource = { Name = 'NPC_Nemesis_01', ObjectId = 810, Accepted = false }
NemesisTradeChoice(staleMenuSource, PresetEventArgs.NemesisBuyItemChoices, {})
assert(CurrentRun.NumRerolls == 5 and panelSpendMutations == 0,
  'closed Nemesis trade changed reroll state')

resetTrade('staleSource', 5)
local staleOwnerSource = { Name = 'NPC_Nemesis_01', ObjectId = 811, Accepted = false }
NemesisTradeChoice(staleOwnerSource, PresetEventArgs.NemesisBuyItemChoices, {})
assert(CurrentRun.NumRerolls == 5 and panelSpendMutations == 0,
  'replaced Nemesis trade source changed reroll state')

-- A modal from a no-longer-current run is a known refusal. The adapter must
-- reject it before native AttemptPanelReroll mutates the replacement run;
-- spend-then-refund is not an acceptable substitute for preflight.
resetTrade('staleRun', 5)
local staleSource = { Name = 'NPC_Nemesis_01', ObjectId = 802, Accepted = false }
NemesisTradeChoice(staleSource, PresetEventArgs.NemesisBuyItemChoices, {})
assert(CurrentRun.NumRerolls == 5,
  'stale Nemesis TradeScreen changed the owning run while refusing')

if MGT_NEMESIS_TERMINAL_SCENARIO == 'postSpendStale' then
  -- If the run changes only after native AttemptPanelReroll has spent, the
  -- transaction outcome is no longer safe to rewrite or refund. Preserve the
  -- completed spend, leave the replacement run untouched, and close the
  -- resident mutation boundary instead of replaying automatically.
  resetTrade('postSpendStale', 5)
  local postSpendSource = { Name = 'NPC_Nemesis_01', ObjectId = 803, Accepted = false }
  NemesisTradeChoice(postSpendSource, PresetEventArgs.NemesisBuyItemChoices, {})
elseif MGT_NEMESIS_TERMINAL_SCENARIO == 'closeFailure' then
  -- Once native spend has happened, an unexpected failure while replacing the
  -- modal is also outcome-unknown. Never refund/replay through an uncertain
  -- partial transaction.
  resetTrade('closeFailure', 5)
  local closeFailureSource = { Name = 'NPC_Nemesis_01', ObjectId = 812, Accepted = false }
  NemesisTradeChoice(closeFailureSource, PresetEventArgs.NemesisBuyItemChoices, {})
elseif MGT_NEMESIS_TERMINAL_SCENARIO == 'initialFailure' then
  resetTrade('initialFailure', 5)
  local initialSource = { Name = 'NPC_Nemesis_01', ObjectId = 814, Accepted = false }
  local ok, message = pcall(NemesisTradeChoice, initialSource,
    PresetEventArgs.NemesisBuyItemChoices, {})
  assert(not ok and not tostring(message):find('MGT_OUTCOME_UNKNOWN', 1, true))
  local observed = M.dispatch('status', { includeCatalogs = false })
  assert(not observed.runtimeOutcomeUnknown and CurrentRun.NumRerolls == 5
    and panelSpendMutations == 0, 'pre-reroll failure falsely closed native trust')
  ShowRerollUI = function() end
  M.dispatch('set_rerolls', { amount = 77, requestId = 'initial-followup', includeCatalogs = false })
elseif MGT_NEMESIS_TERMINAL_SCENARIO == 'redrawFailure' then
  resetTrade('redrawFailure', 5)
  local redrawSource = { Name = 'NPC_Nemesis_01', ObjectId = 813, Accepted = false }
  local ok, message = pcall(NemesisTradeChoice, redrawSource,
    PresetEventArgs.NemesisBuyItemChoices, {})
  assert(not ok and tostring(message):find('MGT_OUTCOME_UNKNOWN', 1, true),
    'replacement TradeScreen failure lost the completed reroll outcome')
  assert(CurrentRun.NumRerolls == 4 and panelSpendMutations == 1,
    'replacement TradeScreen failure guessed a refund')
  local observed = M.dispatch('status', { includeCatalogs = false })
  assert(observed.runtimeOutcomeUnknown and not observed.activeFeatures.forceEnableRerolls)
  assert(observed.featureErrors.forceEnableRerolls == 'hades2.error.outcomeUnknownRuntime',
    'replacement TradeScreen failure lost bilingual feature error')
  ShowRerollUI = function() end
  local mutateOk, mutateError = pcall(M.dispatch, 'set_rerolls', {
    amount = 77, requestId = 'redraw-followup', includeCatalogs = false,
  })
  assert(not mutateOk and tostring(mutateError):find('MGT_OUTCOME_UNKNOWN', 1, true),
    'replacement TradeScreen failure admitted another mutation')
else
  error('unknown Nemesis terminal scenario')
end

-- disable_all above is the only supported teardown while terminal outcome is
-- unknown; no further feature mutation is performed in this harness.

'''

for terminal_scenario in ("postSpendStale", "closeFailure", "initialFailure", "redrawFailure"):
    scenario_cases = (
        f"MGT_NEMESIS_TERMINAL_SCENARIO = '{terminal_scenario}'\n" + NEMESIS_CASES
    )
    harness_text = BASE_HARNESS.replace(
        "print('hades2_force_enable_rerolls_ok')",
        scenario_cases + "\nprint('hades2_force_enable_rerolls_ok')",
    )
    with tempfile.TemporaryDirectory(
        prefix=f"mgt-force-enable-rerolls-nemesis-{terminal_scenario}-"
    ) as temporary:
        harness = Path(temporary) / "force-enable-rerolls-nemesis.lua"
        harness.write_text(harness_text)
        result = subprocess.run(
            [LUA, str(harness), str(ROOT / "Backend/games/hades2/runtime/hades.lua"),
             str(RESIDENT_DISPATCH_CONTRACT)],
            cwd=ROOT, text=True, capture_output=True, timeout=30,
        )
        if result.returncode:
            print(result.stdout)
            print(result.stderr)
            raise SystemExit(result.returncode)
        assert "hades2_force_enable_rerolls_ok" in result.stdout

print("hades2_force_enable_rerolls_nemesis_runtime_ok")
