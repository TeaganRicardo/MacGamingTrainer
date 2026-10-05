import subprocess
import tempfile
from pathlib import Path

from lua_runtime_support import RESIDENT_DISPATCH_CONTRACT, require_lua52

ROOT = Path(__file__).resolve().parents[1]
LUA = require_lua52("Force Enable Rerolls UpgradeChoice behavior")

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
RerollCosts = { Boon = 1, Hammer = 1, ReuseIncrement = 1 }
TraitData = {}
local function copy(value)
  if type(value) ~= 'table' then return value end
  local result = {}; for key, item in pairs(value) do result[key] = copy(item) end; return result
end
DeepCopyTable = copy; ShallowCopyTable = copy
IsGameStateEligible = function() return true end
PassRarityCheck = function() return true end
RemoveRandomValue = function(values) return table.remove(values, 1) end
GetRandomValue = function(values) return values[1] end
RandomSynchronize = function() end
InvalidateCheckpoint = function() end
HideTopMenuScreenTooltips = function() end
ModifyTextBox = function() end
SetAlpha = function() end
RemoveFromGroup = function() end
AddToGroup = function() end
UpdateRerollUI = function() end
IncrementTableValue = function(values, key, amount) values[key] = (values[key] or 0) + amount end
AddInputBlock = function() end
RemoveInputBlock = function() end
PreRerollPanelPresentation = function() end
PostRerollPanelPresentation = function() end
CannotRerollPanelPresentation = function() error('unaffordable native attempt') end
CallFunctionName = function(name, ...) return assert(_G[name], 'missing reroll callback')(... ) end
thread = function(fn, ...) return fn(...) end
wait = function() end

-- Simulate a Chaos Trial / packaged bounty that has stripped the reroll Arcana.
local nativeTraits = {}
HeroHasTrait = function(name) return nativeTraits[name] == true end

local nativeRerolls = 0
RerollBoonLoot = function(screen, button)
  nativeRerolls = nativeRerolls + 1
  local source = button.LootData
  source.UpgradeOptions = {
    { ItemName = 'ChoiceB', Type = 'Trait', Rarity = 'Common' },
    { ItemName = 'ChoiceC', Type = 'Trait', Rarity = 'Common' },
    { ItemName = 'ChoiceD', Type = 'Trait', Rarity = 'Common' },
  }
  CreateBoonLootButtons(screen, source, true)
end

DestroyBoonLootButtons = function(screen) screen.UpgradeButtons = {} end
CreateBoonLootButtons = function(screen, lootData, reroll)
  screen.UpgradeButtons = {}
  for _, option in ipairs(lootData.UpgradeOptions or {}) do
    table.insert(screen.UpgradeButtons, {
      Data = { Name = option.ItemName, Rarity = option.Rarity },
      LootData = lootData,
      OnPressedFunctionName = 'HandleUpgradeChoiceSelection',
    })
  end

  -- Current 1.143476 UpgradeChoiceLogic gate.
  if HeroHasTrait('PanelRerollMetaUpgrade') then
    local cost = -1
    if lootData.BlockReroll then
      cost = -1
    elseif lootData.Name == 'WeaponUpgrade' then
      cost = RerollCosts.Hammer
    else
      cost = RerollCosts.Boon
    end
    local baseCost = cost
    local increment = 0
    if cost >= 0 and CurrentRun.CurrentRoom.SpentRerolls then
      increment = CurrentRun.CurrentRoom.SpentRerolls[lootData.ObjectId] or 0
      cost = cost + increment
    end
    screen.Components.RerollButton.Cost = cost
    if CurrentRun.NumRerolls >= cost and cost >= 0 and baseCost > 0 then
      screen.Components.RerollButton.OnPressedFunctionName = 'AttemptPanelReroll'
      screen.Components.RerollButton.RerollFunctionName = 'RerollBoonLoot'
      screen.Components.RerollButton.RerollId = lootData.ObjectId
      screen.Components.RerollButton.LootData = lootData
      screen.Components.RerollButton.Visible = true
    else
      screen.Components.RerollButton.Visible = false
    end
  end
end

OpenUpgradeChoiceMenu = function(source)
  local screen = {
    Name = 'UpgradeChoice',
    Source = source,
    Components = { RerollButton = { Id = 99, Visible = false }, RerollIcon = { Id = 100 } },
  }
  ActiveScreens.UpgradeChoice = screen
  ScreenAnchors.ChoiceScreen = screen

  -- Current 1.143476 menu-level capability gate.
  if HeroHasTrait('PanelRerollMetaUpgrade') and not source.BlockReroll then
    screen.MovedRerollUIGroup = true
  end
  CreateBoonLootButtons(screen, source, false)
  return screen
end

AttemptPanelReroll = function(screen, button)
  local cost = button.Cost
  assert(cost and cost >= 0 and CurrentRun.NumRerolls >= cost, 'native reroll was not affordable')
  CurrentRun.NumRerolls = CurrentRun.NumRerolls - cost
  CurrentRun.CurrentRoom.SpentRerolls = CurrentRun.CurrentRoom.SpentRerolls or {}
  if button.RerollId then IncrementTableValue(CurrentRun.CurrentRoom.SpentRerolls, button.RerollId, 1) end
  CallFunctionName(button.RerollFunctionName, screen, button)
end

HandleUpgradeChoiceSelection = function() end
GetEligibleUpgrades = function(_, source)
  local result = {}
  for _, name in ipairs(source.Traits or {}) do
    if not HeroHasTrait(name) then result[#result + 1] = { ItemName = name, Type = 'Trait' } end
  end
  return result
end
IsTraitEligible = function(data) return data ~= nil end
HeroSlotFilled = function() return false end
SetTraitsOnLoot = function(source, args)
  source.UpgradeOptions = {}
  for _, name in ipairs(source.Traits or {}) do
    local excluded = args and args.ExclusionNames and args.ExclusionNames[1]
    if name ~= excluded then
      source.UpgradeOptions[#source.UpgradeOptions + 1] = { ItemName = name, Type = 'Trait', Rarity = 'Common' }
      if #source.UpgradeOptions == 3 then break end
    end
  end
end
GetEligibleTransformingTrait = function(values) return copy(values or {}) end
GetProcessedTraitData = function(args) return { Name = args.TraitName, ExtractData = {} } end
SetTraitTextData = function() end
GetHeroTrait = function(name) return CurrentRun.Hero.TraitDictionary[name] end
IsGodTrait = function() return true end

for _, name in ipairs({ 'ChoiceA', 'ChoiceB', 'ChoiceC', 'ChoiceD', 'ChoiceE' }) do
  TraitData[name] = { Name = name, RarityLevels = { Common = {} } }
end
EnemyData = { NPC_Arachne_01 = { Name = 'NPC_Arachne_01' } }
PresetEventArgs = { ArachneCostumeChoices = { UpgradeOptions = {
  { ItemName = 'ChoiceA', Type = 'Trait', Rarity = 'Common' },
  { ItemName = 'ChoiceB', Type = 'Trait', Rarity = 'Common' },
  { ItemName = 'ChoiceC', Type = 'Trait', Rarity = 'Common' },
  { ItemName = 'ChoiceD', Type = 'Trait', Rarity = 'Common' },
  { ItemName = 'ChoiceE', Type = 'Trait', Rarity = 'Common' },
} } }

dofile(assert(arg[1])); dofile(assert(arg[2]))
local M = __MacGamingTrainerV1

assert(CurrentRun.NumRerolls == 10)
local result = M.dispatch('set_feature', { feature = 'forceEnableRerolls', value = true, includeCatalogs = false })
assert(result.desiredFeatures.forceEnableRerolls == true, 'durable desired state missing')
assert(result.activeFeatures.forceEnableRerolls == true, 'force-enable runtime not active')
assert(CurrentRun.NumRerolls == 10, 'enabling force rerolls minted reroll currency')
assert(not HeroHasTrait('PanelRerollMetaUpgrade'), 'feature mutated native trait/progression ownership')

local ordinary = {
  Name = 'ZeusUpgrade', ObjectId = 42,
  Traits = { 'ChoiceA', 'ChoiceB', 'ChoiceC', 'ChoiceD', 'ChoiceE' },
  UpgradeOptions = {
    { ItemName = 'ChoiceA', Type = 'Trait', Rarity = 'Common' },
    { ItemName = 'ChoiceB', Type = 'Trait', Rarity = 'Common' },
    { ItemName = 'ChoiceC', Type = 'Trait', Rarity = 'Common' },
  },
}
LootData.ZeusUpgrade = { GodLoot = true }
local ordinaryScreen = OpenUpgradeChoiceMenu(ordinary)
assert(ordinaryScreen.MovedRerollUIGroup, 'trial-disabled panel reroll capability was not force-enabled')
assert(ordinaryScreen.Components.RerollButton.Visible
  and ordinaryScreen.Components.RerollButton.OnPressedFunctionName == 'AttemptPanelReroll',
  'game-owned reroll control was not exposed')
assert(ordinaryScreen.Components.RerollButton.RerollFunctionName == 'RerollBoonLoot',
  'ordinary native generator was replaced unnecessarily')
CallFunctionName(ordinaryScreen.Components.RerollButton.OnPressedFunctionName,
  ordinaryScreen, ordinaryScreen.Components.RerollButton)
assert(CurrentRun.NumRerolls == 9 and nativeRerolls == 1,
  'native AttemptPanelReroll did not own one spend and native regeneration')

CurrentRun.NumRerolls = 10
CurrentRun.CurrentRoom.SpentRerolls = {}
local fixed = copy(EnemyData.NPC_Arachne_01)
fixed.ObjectId = 77
fixed.BlockReroll = true
fixed.UpgradeOptions = {
  copy(PresetEventArgs.ArachneCostumeChoices.UpgradeOptions[1]),
  copy(PresetEventArgs.ArachneCostumeChoices.UpgradeOptions[2]),
  copy(PresetEventArgs.ArachneCostumeChoices.UpgradeOptions[3]),
}
local fixedScreen = OpenUpgradeChoiceMenu(fixed)
assert(fixedScreen.MovedRerollUIGroup, 'BlockReroll fixed owner did not expose native reroll UI')
assert(fixedScreen.Components.RerollButton.Visible
  and fixedScreen.Components.RerollButton.OnPressedFunctionName == 'AttemptPanelReroll',
  'fixed owner did not retain the native reroll action')
assert(fixedScreen.Components.RerollButton.RerollFunctionName ~= 'RerollBoonLoot',
  'fixed owner incorrectly fell through the generic native generator')
CallFunctionName(fixedScreen.Components.RerollButton.OnPressedFunctionName,
  fixedScreen, fixedScreen.Components.RerollButton)
assert(CurrentRun.NumRerolls == 9, 'fixed owner did not spend through native AttemptPanelReroll')
assert(fixed.UpgradeOptions[3].ItemName == 'ChoiceD',
  'fixed owner adapter did not generate a changed eligible candidate set')

M.dispatch('set_feature', { feature = 'forceEnableRerolls', value = false, includeCatalogs = false })
CurrentRun.NumRerolls = 10
CurrentRun.CurrentRoom.SpentRerolls = {}
local disabled = copy(EnemyData.NPC_Arachne_01)
disabled.ObjectId = 88
disabled.BlockReroll = true
disabled.UpgradeOptions = {
  copy(PresetEventArgs.ArachneCostumeChoices.UpgradeOptions[1]),
  copy(PresetEventArgs.ArachneCostumeChoices.UpgradeOptions[2]),
  copy(PresetEventArgs.ArachneCostumeChoices.UpgradeOptions[3]),
}
local disabledScreen = OpenUpgradeChoiceMenu(disabled)
assert(not disabledScreen.MovedRerollUIGroup and not disabledScreen.Components.RerollButton.Visible,
  'disabling Force Enable Rerolls did not restore native availability rules')

local oldCommandOk = pcall(M.dispatch, 'reroll_choice', {
  requestId = 'obsolete-trainer-action', menuToken = 'obsolete', expectedCost = 1, includeCatalogs = false,
})
assert(not oldCommandOk, 'obsolete Trainer-issued reroll_choice command is still exposed')

print('hades2_force_enable_rerolls_ok')
'''

with tempfile.TemporaryDirectory(prefix='mgt-force-enable-rerolls-') as temporary:
    harness = Path(temporary) / 'force-enable-rerolls.lua'
    harness.write_text(HARNESS)
    result = subprocess.run(
        [LUA, str(harness), str(ROOT / 'Backend/games/hades2/runtime/hades.lua'),
         str(RESIDENT_DISPATCH_CONTRACT)],
        cwd=ROOT, text=True, capture_output=True, timeout=30,
    )
    if result.returncode:
        print(result.stdout)
        print(result.stderr)
        raise SystemExit(result.returncode)
    assert 'hades2_force_enable_rerolls_ok' in result.stdout

print('hades2_force_enable_rerolls_runtime_ok')
