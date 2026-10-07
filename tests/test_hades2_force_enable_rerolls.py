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
ScreenState = {}; ScreenAnchors = { Reroll = 101 }; ActiveScreens = {}
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
local rerollIconAlpha = 0
local rerollGroup = 'Combat_UI'
SetAlpha = function(args)
  if args.Id == 100 then rerollIconAlpha = args.Fraction end
end
RemoveFromGroup = function(args)
  if args.Id == ScreenAnchors.Reroll then rerollGroup = nil end
end
AddToGroup = function(args)
  if args.Id == ScreenAnchors.Reroll then rerollGroup = args.Name end
end
UpdateRerollUI = function() end
IncrementTableValue = function(values, key, amount) values[key] = (values[key] or 0) + amount end
AddInputBlock = function() end
RemoveInputBlock = function() end
PreRerollPanelPresentation = function() end
PostRerollPanelPresentation = function() end
CannotRerollPanelPresentation = function() error('unaffordable native attempt') end
CallFunctionName = function(name, ...) return assert(_G[name], 'missing reroll callback')(... ) end
thread = function(fn, ...) return fn(...) end

-- Hades' real panel reroll owner yields through wait(). Track protected-call
-- depth so this fixture fails if the Trainer ever wraps that game coroutine
-- in pcall/nativeOperations again.
local rawPcall = pcall
local protectedCallDepth = 0
local enforceNativePanelYieldBoundary = false
local function pack(...)
  return { n = select('#', ...), ... }
end
pcall = function(fn, ...)
  protectedCallDepth = protectedCallDepth + 1
  local result = pack(rawPcall(fn, ...))
  protectedCallDepth = protectedCallDepth - 1
  return unpack(result, 1, result.n)
end
wait = function()
  if enforceNativePanelYieldBoundary then
    assert(protectedCallDepth == 0,
      'game-owned AttemptPanelReroll wait crossed a Trainer protected-call boundary')
  end
end

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
  UpdateRerollUI(CurrentRun.NumRerolls)

  -- Match the 1.143476 owner shape: both presentation phases and the outer
  -- AttemptPanelReroll lifecycle yield around the callback.
  ScreenState.InTransition = true
  PreRerollPanelPresentation(screen, button)
  wait(0.51)
  CallFunctionName(button.RerollFunctionName, screen, button)
  PostRerollPanelPresentation(screen, button)
  wait(0.40)
  wait(0.10)
  wait(0.95)
  ScreenState.InTransition = false
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
  TraitData[name] = { Name = name, RarityLevels = { Common = {}, Epic = {} } }
end
local basePool = {
  { ItemName = 'ChoiceA', Type = 'Trait', Rarity = 'Common' },
  { ItemName = 'ChoiceB', Type = 'Trait', Rarity = 'Common' },
  { ItemName = 'ChoiceC', Type = 'Trait', Rarity = 'Common' },
  { ItemName = 'ChoiceD', Type = 'Trait', Rarity = 'Common' },
  { ItemName = 'ChoiceE', Type = 'Trait', Rarity = 'Common' },
}
EnemyData = {
  NPC_Arachne_01 = { Name = 'NPC_Arachne_01' },
  NPC_Narcissus_01 = { Name = 'NPC_Narcissus_01' },
  NPC_Echo_01 = { Name = 'NPC_Echo_01' },
  NPC_Medea_01 = { Name = 'NPC_Medea_01' },
  NPC_Circe_01 = { Name = 'NPC_Circe_01' },
  NPC_Icarus_01 = { Name = 'NPC_Icarus_01' },
  NPC_Artemis_Field_01 = { Name = 'NPC_Artemis_Field_01', Traits = { 'ChoiceA', 'ChoiceB', 'ChoiceC', 'ChoiceD', 'ChoiceE' } },
  NPC_Athena_01 = { Name = 'NPC_Athena_01', Traits = { 'ChoiceA', 'ChoiceB', 'ChoiceC', 'ChoiceD', 'ChoiceE' } },
  NPC_Dionysus_01 = { Name = 'NPC_Dionysus_01', Traits = { 'ChoiceA', 'ChoiceB', 'ChoiceC', 'ChoiceD', 'ChoiceE' } },
  NPC_Hades_Field_01 = { Name = 'NPC_Hades_Field_01', Traits = { 'ChoiceA', 'ChoiceB', 'ChoiceC', 'ChoiceD', 'ChoiceE' } },
}
PresetEventArgs = {
  ArachneCostumeChoices = { UpgradeOptions = copy(basePool) },
  NarcissusBenefitChoices = { UpgradeOptions = copy(basePool) },
  EchoBenefitChoices = { UpgradeOptions = copy(basePool) },
  MedeaCurseChoices = { UpgradeOptions = copy(basePool) },
  CirceBlessingChoices = { UpgradeOptions = copy(basePool) },
  IcarusBenefitChoices = { UpgradeOptions = copy(basePool) },
}

dofile(assert(arg[1])); dofile(assert(arg[2]))
local M = __MacGamingTrainerV1

assert(CurrentRun.NumRerolls == 10)
local result = M.dispatch('set_feature', { feature = 'forceEnableRerolls', value = true, includeCatalogs = false })
assert(result.desiredFeatures.forceEnableRerolls == true, 'durable desired state missing')
assert(result.activeFeatures.forceEnableRerolls == true, 'force-enable runtime not active')
assert(CurrentRun.NumRerolls == 10, 'enabling force rerolls minted reroll currency')
assert(not HeroHasTrait('PanelRerollMetaUpgrade'), 'feature mutated native trait/progression ownership')

local ordinary = {
  Name = 'HeraUpgrade', ObjectId = 42,
  Traits = { 'ChoiceA', 'ChoiceB', 'ChoiceC', 'ChoiceD', 'ChoiceE' },
  UpgradeOptions = {
    { ItemName = 'ChoiceA', Type = 'Trait', Rarity = 'Common' },
    { ItemName = 'ChoiceB', Type = 'Trait', Rarity = 'Common' },
    { ItemName = 'ChoiceC', Type = 'Trait', Rarity = 'Common' },
  },
}
LootData.HeraUpgrade = { GodLoot = true }
LootData.ZeusUpgrade = { GodLoot = true }
local ordinaryScreen = OpenUpgradeChoiceMenu(ordinary)
assert(ordinaryScreen.MovedRerollUIGroup, 'trial-disabled panel reroll capability was not force-enabled')
assert(ordinaryScreen.Components.RerollButton.Visible
  and ordinaryScreen.Components.RerollButton.OnPressedFunctionName == 'AttemptPanelReroll',
  'game-owned reroll control was not exposed')
assert(ordinaryScreen.Components.RerollButton.RerollFunctionName == 'RerollBoonLoot',
  'ordinary native generator was replaced unnecessarily')
enforceNativePanelYieldBoundary = true
CallFunctionName(ordinaryScreen.Components.RerollButton.OnPressedFunctionName,
  ordinaryScreen, ordinaryScreen.Components.RerollButton)
enforceNativePanelYieldBoundary = false
assert(CurrentRun.NumRerolls == 9 and nativeRerolls == 1,
  'native AttemptPanelReroll did not own one spend and native regeneration')
assert(ordinaryScreen.Components.RerollButton.Cost == 2,
  'native room/source cost history did not escalate through the game-owned button')
local ordinaryStatus = M.dispatch('status', { includeCatalogs = false })
assert(not ordinaryStatus.runtimeOutcomeUnknown
  and ordinaryStatus.activeFeatures.forceEnableRerolls,
  'ordinary Hera reroll poisoned resident trust')

-- Every native UpgradeChoice loot owner keeps the native reroll generator.
for index, name in ipairs({ 'HermesUpgrade', 'StackUpgrade', 'TrialUpgrade' }) do
  CurrentRun.NumRerolls = 10
  CurrentRun.CurrentRoom.SpentRerolls = {}
  local source = {
    Name = name, ObjectId = 100 + index,
    Traits = { 'ChoiceA', 'ChoiceB', 'ChoiceC', 'ChoiceD', 'ChoiceE' },
    UpgradeOptions = { copy(basePool[1]), copy(basePool[2]), copy(basePool[3]) },
  }
  local screen = OpenUpgradeChoiceMenu(source)
  assert(screen.Components.RerollButton.Visible
    and screen.Components.RerollButton.RerollFunctionName == 'RerollBoonLoot',
    name .. ' did not retain native UpgradeChoice reroll ownership')
end

-- Hammer is force-enabled even when the native target reports its normal negative reroll cost.
RerollCosts.Hammer = -1
CurrentRun.NumRerolls = 10
CurrentRun.CurrentRoom.SpentRerolls = {}
local hammer = {
  Name = 'WeaponUpgrade', ObjectId = 150,
  Traits = { 'ChoiceA', 'ChoiceB', 'ChoiceC', 'ChoiceD', 'ChoiceE' },
  UpgradeOptions = { copy(basePool[1]), copy(basePool[2]), copy(basePool[3]) },
}
local hammerScreen = OpenUpgradeChoiceMenu(hammer)
assert(hammerScreen.Components.RerollButton.Visible and hammerScreen.Components.RerollButton.Cost == 1
  and hammerScreen.Components.RerollButton.RerollFunctionName == 'RerollBoonLoot',
  'force-enabled Hammer did not use the ordinary reroll base cost with native regeneration')
RerollCosts.Hammer = 1

-- Natural loot special-NPC UpgradeChoice owners keep the native generator.
for index, npc in ipairs({
  'NPC_Artemis_Field_01', 'NPC_Athena_01', 'NPC_Dionysus_01', 'NPC_Hades_Field_01',
}) do
  CurrentRun.NumRerolls = 10
  CurrentRun.CurrentRoom.SpentRerolls = {}
  local source = copy(EnemyData[npc])
  source.ObjectId = 200 + index
  source.UpgradeOptions = { copy(basePool[1]), copy(basePool[2]), copy(basePool[3]) }
  local screen = OpenUpgradeChoiceMenu(source)
  assert(screen.Components.RerollButton.Visible
    and screen.Components.RerollButton.RerollFunctionName == 'RerollBoonLoot',
    npc .. ' did not retain native loot reroll ownership')
end

local fixedOwners = {
  { 'NPC_Arachne_01', 'ArachneCostumeChoices' },
  { 'NPC_Narcissus_01', 'NarcissusBenefitChoices' },
  { 'NPC_Echo_01', 'EchoBenefitChoices' },
  { 'NPC_Medea_01', 'MedeaCurseChoices' },
  { 'NPC_Circe_01', 'CirceBlessingChoices' },
  { 'NPC_Icarus_01', 'IcarusBenefitChoices' },
}
for index, row in ipairs(fixedOwners) do
  CurrentRun.NumRerolls = 10
  CurrentRun.CurrentRoom.SpentRerolls = {}
  local fixed = copy(EnemyData[row[1]])
  fixed.ObjectId = 300 + index
  fixed.BlockReroll = true
  fixed.UpgradeOptions = {
    copy(PresetEventArgs[row[2]].UpgradeOptions[1]),
    copy(PresetEventArgs[row[2]].UpgradeOptions[2]),
    copy(PresetEventArgs[row[2]].UpgradeOptions[3]),
  }
  local before = fixed.UpgradeOptions[1].ItemName .. fixed.UpgradeOptions[2].ItemName .. fixed.UpgradeOptions[3].ItemName
  local fixedScreen = OpenUpgradeChoiceMenu(fixed)
  assert(fixedScreen.MovedRerollUIGroup, row[1] .. ' BlockReroll did not expose native reroll UI')
  assert(fixedScreen.Components.RerollButton.Visible
    and fixedScreen.Components.RerollButton.OnPressedFunctionName == 'AttemptPanelReroll',
    row[1] .. ' did not retain the native reroll action')
  assert(fixedScreen.Components.RerollButton.RerollFunctionName ~= 'RerollBoonLoot',
    row[1] .. ' incorrectly fell through the generic native generator')
  CallFunctionName(fixedScreen.Components.RerollButton.OnPressedFunctionName,
    fixedScreen, fixedScreen.Components.RerollButton)
  local after = fixed.UpgradeOptions[1].ItemName .. fixed.UpgradeOptions[2].ItemName .. fixed.UpgradeOptions[3].ItemName
  assert(CurrentRun.NumRerolls == 9 and before ~= after,
    row[1] .. ' fixed owner did not spend once and present changed candidates')
end

-- Echo previous-run is a distinct candidate owner even though it shares the Echo NPC.
GameState.RunHistory = { { TraitRarityCache = {
  ChoiceA = 'Common', ChoiceB = 'Common', ChoiceC = 'Common', ChoiceD = 'Common', ChoiceE = 'Common',
} } }
CurrentRun.NumRerolls = 10
CurrentRun.CurrentRoom.SpentRerolls = {}
local previous = {
  Name = 'NPC_Echo_01', ObjectId = 390, MenuTitle = 'EchoChoiceMenu_LastRun',
  OnPressedFunctionNameOverride = 'SelectEchoBoon', BlockReroll = true,
  UpgradeOptions = { copy(basePool[1]), copy(basePool[2]), copy(basePool[3]) },
}
local previousBefore = previous.UpgradeOptions[1].ItemName .. previous.UpgradeOptions[2].ItemName .. previous.UpgradeOptions[3].ItemName
local previousScreen = OpenUpgradeChoiceMenu(previous)
assert(previousScreen.Components.RerollButton.Visible
  and previousScreen.Components.RerollButton.RerollFunctionName ~= 'RerollBoonLoot',
  'Echo previous-run did not use its owner-specific native-button adapter')
CallFunctionName(previousScreen.Components.RerollButton.OnPressedFunctionName,
  previousScreen, previousScreen.Components.RerollButton)
local previousAfter = previous.UpgradeOptions[1].ItemName .. previous.UpgradeOptions[2].ItemName .. previous.UpgradeOptions[3].ItemName
assert(previousBefore ~= previousAfter and CurrentRun.NumRerolls == 9,
  'Echo previous-run reroll did not change candidates through native spend')

-- Synthetic special-loot sources keep game selection UI but adapt generation back to the native NPC owner.
CurrentRun.NumRerolls = 10
CurrentRun.CurrentRoom.SpentRerolls = {}
local synthetic = copy(EnemyData.NPC_Artemis_Field_01)
synthetic.Name = 'MacGamingTrainerSpecial_Artemis'
synthetic.ObjectId = -1
synthetic.BlockReroll = true
synthetic.UpgradeOptions = { copy(basePool[1]), copy(basePool[2]), copy(basePool[3]) }
local syntheticScreen = OpenUpgradeChoiceMenu(synthetic)
assert(syntheticScreen.Components.RerollButton.Visible
  and syntheticScreen.Components.RerollButton.RerollFunctionName ~= 'RerollBoonLoot',
  'synthetic special loot did not route through its native-owner adapter')
CallFunctionName(syntheticScreen.Components.RerollButton.OnPressedFunctionName,
  syntheticScreen, syntheticScreen.Components.RerollButton)
assert(CurrentRun.NumRerolls == 9 and synthetic.UpgradeOptions[3].ItemName == 'ChoiceD',
  'synthetic special loot reroll did not spend once and regenerate through owner data')

-- A structurally exhausted fixed pool stays non-actionable instead of spending for a fake reroll.
local fullArachnePool = PresetEventArgs.ArachneCostumeChoices.UpgradeOptions
PresetEventArgs.ArachneCostumeChoices.UpgradeOptions = {
  copy(basePool[1]), copy(basePool[2]), copy(basePool[3]),
}
CurrentRun.NumRerolls = 10
local exhausted = copy(EnemyData.NPC_Arachne_01)
exhausted.ObjectId = 399
exhausted.BlockReroll = true
exhausted.UpgradeOptions = {
  copy(basePool[1]), copy(basePool[2]), copy(basePool[3]),
}
local exhaustedScreen = OpenUpgradeChoiceMenu(exhausted)
assert(not exhaustedScreen.Components.RerollButton.Visible
  and exhaustedScreen.Components.RerollButton.OnPressedFunctionName == nil,
  'fixed pool with no alternative exposed a spendable fake reroll')
assert(CurrentRun.NumRerolls == 10, 'exhausted pool changed reroll currency')
PresetEventArgs.ArachneCostumeChoices.UpgradeOptions = fullArachnePool

-- Existing reroll lock remains independent: native spend is immediately reconciled to the locked count.
CurrentRun.NumRerolls = 10
CurrentRun.CurrentRoom.SpentRerolls = {}
M.dispatch('lock_rerolls', { requestId = 'lock-count', locked = true, includeCatalogs = false })
local lockedSource = {
  Name = 'ZeusUpgrade', ObjectId = 401,
  Traits = { 'ChoiceA', 'ChoiceB', 'ChoiceC', 'ChoiceD', 'ChoiceE' },
  UpgradeOptions = { copy(basePool[1]), copy(basePool[2]), copy(basePool[3]) },
}
local lockedScreen = OpenUpgradeChoiceMenu(lockedSource)
CallFunctionName(lockedScreen.Components.RerollButton.OnPressedFunctionName,
  lockedScreen, lockedScreen.Components.RerollButton)
assert(CurrentRun.NumRerolls == 10 and M.rerollsLock == 10,
  'Force Enable Rerolls broke independent reroll-count lock semantics')
M.dispatch('lock_rerolls', { requestId = 'unlock-count', locked = false, includeCatalogs = false })

-- The durable toggle can also be turned on while a supported native page is already open.
M.dispatch('set_feature', { feature = 'forceEnableRerolls', value = false, includeCatalogs = false })
CurrentRun.NumRerolls = 10
CurrentRun.CurrentRoom.SpentRerolls = {}
local alreadyOpen = {
  Name = 'ZeusUpgrade', ObjectId = 450,
  Traits = { 'ChoiceA', 'ChoiceB', 'ChoiceC', 'ChoiceD', 'ChoiceE' },
  UpgradeOptions = { copy(basePool[1]), copy(basePool[2]), copy(basePool[3]) },
}
local alreadyOpenScreen = OpenUpgradeChoiceMenu(alreadyOpen)
assert(not alreadyOpenScreen.Components.RerollButton.Visible,
  'native-disabled page unexpectedly exposed reroll before feature enable')
M.dispatch('set_feature', { feature = 'forceEnableRerolls', value = true, includeCatalogs = false })
assert(alreadyOpenScreen.Components.RerollButton.Visible
  and alreadyOpenScreen.Components.RerollButton.OnPressedFunctionName == 'AttemptPanelReroll',
  'enabling feature did not activate the already-open supported native page')
assert(rerollGroup == 'Combat_Menu_Overlay' and rerollIconAlpha == 1.0,
  'enabling feature did not move and reveal the native reroll UI')

M.dispatch('set_feature', { feature = 'forceEnableRerolls', value = false, includeCatalogs = false })
assert(not alreadyOpenScreen.Components.RerollButton.Visible,
  'disabling feature did not restore native availability on the current page')
assert(rerollGroup == 'Combat_UI' and rerollIconAlpha == 0.0
  and alreadyOpenScreen.MovedRerollUIGroup == nil,
  'disabling feature left forced reroll UI presentation active on the current page')
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
