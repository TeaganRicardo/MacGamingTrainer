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
IncrementTableValue = function(values, key, amount)
  panelSpendMutations = panelSpendMutations + 1
  values[key] = (values[key] or 0) + amount
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

local tradeOpenCount = 0
local tradeMode = 'money'
local displayedReward
local displayedCost
local settledReward
local settledCost

CloseTradeScreen = function(screen)
  screen.KeepOpen = false
  if ActiveScreens.TradeScreen == screen then ActiveScreens.TradeScreen = nil end
end

HandleScreenInput = function(screen)
  assert(screen.Name == 'TradeScreen')
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
  if tradeOpenCount == 1 then
    local button = screen.Components.RerollButton
    assert(type(button) == 'table' and button.Visible
      and button.OnPressedFunctionName == 'AttemptPanelReroll',
      'Nemesis TradeScreen did not expose the native-style forced reroll action')
    assert(randomChoiceCalls == 2,
      'opening a Nemesis trade consumed RNG beyond native give/get selection')
    local before = screen.ChosenGetOption.Name
    CallFunctionName(button.OnPressedFunctionName, screen, button)
    assert(randomChoiceCalls == 4,
      'Nemesis trade reroll did not regenerate through native-shaped give/get draws')
    assert(not screen.KeepOpen, 'Nemesis trade reroll did not close the old native screen before redraw')
    assert(screen.ChosenGetOption.Name == before,
      'Nemesis trade reroll mutated the already-presented transaction plan in place')
  else
    displayedReward = screen.ChosenGetOption.Name
    displayedCost = screen.ChosenGiveOption.Cost
    screen.Source.Accepted = true
    CloseTradeScreen(screen)
  end
end

OpenTradeScreen = function(source, args, chosenGiveOption, chosenGetOption)
  tradeOpenCount = tradeOpenCount + 1
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

  if chosenGiveOption.UseGetCost then
    chosenGiveOption.Cost = RandomInt(
      chosenGetOption.CostResourceMin,
      chosenGetOption.CostResourceMax
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
  if giveOption.UseGetCost then
    SpendResource(getOption.CostResourceName, giveOption.Cost)
  end
  settledReward = getOption.Name
  settledCost = giveOption.Cost
end

GameState.Resources.Money = 100
CurrentRun.NumRerolls = 5
CurrentRun.CurrentRoom.SpentRerolls = {}
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

-- A modal from a no-longer-current run is a known refusal. The adapter must
-- reject it before native AttemptPanelReroll mutates the replacement run;
-- spend-then-refund is not an acceptable substitute for preflight.
tradeMode = 'staleRun'
tradeOpenCount = 0
randomChoiceCalls = 0
panelSpendMutations = 0
CurrentRun.NumRerolls = 5
CurrentRun.CurrentRoom.SpentRerolls = {}
local staleSource = { Name = 'NPC_Nemesis_01', ObjectId = 802, Accepted = false }
NemesisTradeChoice(staleSource, PresetEventArgs.NemesisBuyItemChoices, {})
assert(CurrentRun.NumRerolls == 5,
  'stale Nemesis TradeScreen changed the owning run while refusing')

M.dispatch('set_feature', { feature = 'forceEnableRerolls', value = false, includeCatalogs = false })
'''

HARNESS = BASE_HARNESS.replace(
    "print('hades2_force_enable_rerolls_ok')",
    NEMESIS_CASES + "\nprint('hades2_force_enable_rerolls_ok')",
)

with tempfile.TemporaryDirectory(prefix="mgt-force-enable-rerolls-nemesis-") as temporary:
    harness = Path(temporary) / "force-enable-rerolls-nemesis.lua"
    harness.write_text(HARNESS)
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
