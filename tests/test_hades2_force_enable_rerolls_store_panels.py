import subprocess
import tempfile
from pathlib import Path

from lua_runtime_support import RESIDENT_DISPATCH_CONTRACT, require_lua52

ROOT = Path(__file__).resolve().parents[1]
LUA = require_lua52("Force Enable Rerolls store-panel behavior")

SOURCE = (ROOT / "tests/test_hades2_force_enable_rerolls.py").read_text()
START = SOURCE.index("HARNESS = r'''") + len("HARNESS = r'''")
END = SOURCE.index("\n'''\n\nwith tempfile", START)
BASE_HARNESS = SOURCE[START:END]

STORE_STUBS = r'''
RerollCosts.Shop = 1
CurrentRun.CurrentRoom.Store = {
  StoreOptions = {
    { Name = 'StoreA' },
    { Name = 'StoreB' },
    { Name = 'StoreC' },
  },
}
CurrentRun.CurrentRoom.IndexesPurchased = {}
CurrentRun.CurrentRoom.SellOptions = {
  { Name = 'ChoiceA', Value = 100, Rarity = 'Common' },
  { Name = 'ChoiceB', Value = 110, Rarity = 'Rare' },
  { Name = 'ChoiceC', Value = 120, Rarity = 'Epic' },
}
CurrentRun.CurrentRoom.SellValues = {
  ChoiceA = { Name = 'ChoiceA', Value = 100, Rarity = 'Common' },
  ChoiceB = { Name = 'ChoiceB', Value = 110, Rarity = 'Rare' },
  ChoiceC = { Name = 'ChoiceC', Value = 120, Rarity = 'Epic' },
  ChoiceD = { Name = 'ChoiceD', Value = 130, Rarity = 'Rare' },
}

-- Shrine of Hermes is a distinct SurfaceShop owner. Unlike WellShop and
-- SellTraits, the native screen has no reroll components of its own.
local nextComponentId = 1300
local function component()
  nextComponentId = nextComponentId + 1
  return { Id = nextComponentId, Visible = false }
end
CreateComponentFromData = function(screenData, data)
  local value = component()
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
UpdateStoreOptionsDictionary = function() end
ScreenData.UpgradeChoice = {
  ComponentData = {
    RerollIcon = { Animation = 'RerollIcon', Alpha = 0 },
    ActionBar = {
      Children = {
        RerollButton = {
          Graphic = 'ContextualActionButton', Alpha = 0,
          Data = { OnPressedFunctionName = 'AttemptPanelReroll', ControlHotkeys = { 'Reroll' } },
          Text = ' ', AltText = 'Boon_Reroll',
        },
      },
    },
  },
}
ScreenData.SurfaceShop = {
  ComponentData = {
    ActionBar = {
      ChildrenOrder = { 'CloseButton', 'TraitTrayButton', 'SelectButton' },
      Children = { CloseButton = {}, TraitTrayButton = {}, SelectButton = {} },
      AutoAlignJustification = 'Right',
    },
  },
}
StoreData = {
  SurfaceShop = {
    GroupsOf = {
      { WeightedList = true, Offers = 1, OptionsData = {
        { Name = 'StoreA' }, { Name = 'StoreD' },
      } },
      { WeightedList = true, Offers = 2, OptionsData = {
        { Name = 'StoreB' }, { Name = 'StoreC' }, { Name = 'StoreE' },
        { Name = 'StoreF' }, { Name = 'StoreG' }, { Name = 'StoreH' },
      } },
    },
  },
}
for _, name in ipairs({ 'StoreA','StoreB','StoreC','StoreD','StoreE','StoreF','StoreG','StoreH' }) do
  ConsumableData[name] = { Name = name }
end
StoreItemEligible = function() return true end
local function excluded(names)
  local result = {}
  for _, name in ipairs(names or {}) do result[name] = true end
  return result
end
FillInShopOptions = function(args)
  local result = { StoreOptions = {} }
  local blocked = excluded(args.ExclusionNames)
  for _, group in ipairs(args.StoreData.GroupsOf or {}) do
    local wanted = group.Offers or 0
    for _, item in ipairs(group.OptionsData or {}) do
      if wanted <= 0 then break end
      if not blocked[item.Name] then
        result.StoreOptions[#result.StoreOptions + 1] = { Name = item.Name, Type = 'Consumable' }
        blocked[item.Name] = true
        wanted = wanted - 1
      end
    end
    if wanted > 0 then return { StoreOptions = {} } end
  end
  return result
end
CreateSurfaceShopButtons = function(screen)
  CurrentRun.CurrentRoom.Store.Buttons = {}
  for index, option in pairs(CurrentRun.CurrentRoom.Store.StoreOptions or {}) do
    if option then
      local button = component()
      button.Screen = screen; button.Index = index; button.Data = option
      screen.Components['PurchaseButton'..index] = button
      for _, key in ipairs({
        'PurchaseButton'..index..'Highlight', 'Icon'..index, 'IconBacking'..index,
        'Backing'..index, 'HermesSpeedUp'..index, 'PurchaseButtonCost'..index,
        'PurchaseButtonTitle'..index, 'PurchaseButtonDelivery'..index,
      }) do screen.Components[key] = component() end
      CurrentRun.CurrentRoom.Store.Buttons[#CurrentRun.CurrentRoom.Store.Buttons + 1] = button
    end
  end
end
HandleSurfaceShopAction = function(screen, button)
  local option = CurrentRun.CurrentRoom.Store.StoreOptions[button.Index]
  if option then option.Purchased = true end
end

local storeRerolls = 0
local sellRerolls = 0

UpdateStoreReroll = function(screen, options, rerollFunctionName)
  local components = screen.Components
  options = options or CurrentRun.CurrentRoom.Store.StoreOptions
  local hasOptions = type(options) == 'table' and next(options) ~= nil
  if HeroHasTrait('PanelRerollMetaUpgrade') and hasOptions then
    local increment = 0
    if CurrentRun.CurrentRoom.SpentRerolls then
      increment = CurrentRun.CurrentRoom.SpentRerolls[screen.Name] or 0
    end
    local cost = RerollCosts.Shop + increment
    components.RerollButton.Cost = cost
    components.RerollButton.RerollId = screen.Name
    if CurrentRun.NumRerolls >= cost and cost > 0 then
      components.RerollButton.RerollFunctionName = rerollFunctionName or 'RerollStore'
      components.RerollButton.OnPressedFunctionName = 'AttemptPanelReroll'
      components.RerollButton.Visible = true
    else
      components.RerollButton.RerollFunctionName = nil
      components.RerollButton.Visible = false
    end
  else
    components.RerollButton.RerollFunctionName = nil
    components.RerollButton.Visible = false
  end
end

RerollStore = function(screen, button)
  storeRerolls = storeRerolls + 1
  CurrentRun.CurrentRoom.Store.StoreOptions = {
    { Name = 'StoreD' },
    { Name = 'StoreE' },
    { Name = 'StoreF' },
  }
  UpdateStoreReroll(screen)
end

SellTraitScreenReroll = function(screen, button)
  sellRerolls = sellRerolls + 1
  CurrentRun.CurrentRoom.SellOptions = {
    { Name = 'ChoiceB', Value = 110, Rarity = 'Rare' },
    { Name = 'ChoiceC', Value = 120, Rarity = 'Epic' },
    { Name = 'ChoiceD', Value = 130, Rarity = 'Rare' },
  }
  UpdateStoreReroll(screen, CurrentRun.CurrentRoom.SellOptions, 'SellTraitScreenReroll')
end

local function openPanel(name, rerollFunctionName)
  local screen = {
    Name = name,
    Components = {
      RerollButton = { Id = name == 'WellShop' and 1001 or 1002, Visible = false },
    },
    KeepOpen = true,
  }
  ActiveScreens[name] = screen
  if name == 'WellShop' then
    UpdateStoreReroll(screen)
  else
    UpdateStoreReroll(screen, CurrentRun.CurrentRoom.SellOptions, rerollFunctionName)
  end
  return screen
end
'''

BASE_HARNESS = BASE_HARNESS.replace(
    "dofile(assert(arg[1])); dofile(assert(arg[2]))",
    STORE_STUBS + "\ndofile(assert(arg[1])); dofile(assert(arg[2]))",
)

STORE_CASES = r'''
M.dispatch('set_feature', { feature = 'forceEnableRerolls', value = false, includeCatalogs = false })
ScreenAnchors.ChoiceScreen = nil
ActiveScreens.UpgradeChoice = nil
nativeTraits.PanelRerollMetaUpgrade = nil
CurrentRun.NumRerolls = 8
CurrentRun.CurrentRoom.SpentRerolls = {}

local well = openPanel('WellShop')
local sell = openPanel('SellTraits', 'SellTraitScreenReroll')
local surface = {
  Name = 'SurfaceShop',
  Components = { ActionBar = { Id = 1200 } },
  KeepOpen = true,
}
ActiveScreens.SurfaceShop = surface
CreateSurfaceShopButtons(surface)
assert(surface.Components.RerollButton == nil,
  'native SurfaceShop fixture unexpectedly started with a reroll control')
assert(not well.Components.RerollButton.Visible
  and not sell.Components.RerollButton.Visible,
  'trial-disabled store panels unexpectedly exposed reroll before feature enable')

M.dispatch('set_feature', { feature = 'forceEnableRerolls', value = true, includeCatalogs = false })
assert(well.Components.RerollButton.Visible
  and well.Components.RerollButton.RerollFunctionName == 'RerollStore'
  and well.Components.RerollButton.OnPressedFunctionName == 'AttemptPanelReroll',
  'enabling Force Enable Rerolls did not activate an already-open WellShop')
assert(sell.Components.RerollButton.Visible
  and sell.Components.RerollButton.RerollFunctionName == 'SellTraitScreenReroll'
  and sell.Components.RerollButton.OnPressedFunctionName == 'AttemptPanelReroll',
  'enabling Force Enable Rerolls did not activate an already-open SellTraits panel')
assert(not HeroHasTrait('PanelRerollMetaUpgrade'),
  'store-panel force enable mutated or globally spoofed native panel-trait ownership outside owner recompute')
assert(type(surface.Components.RerollButton) == 'table'
  and surface.Components.RerollButton.Visible
  and surface.Components.RerollButton.OnPressedFunctionName == 'AttemptPanelReroll',
  'enabling Force Enable Rerolls did not add the reroll control to an already-open Shrine of Hermes')
assert(surface.Components.RerollButton.RerollFunctionName ~= nil
  and surface.Components.RerollButton.RerollFunctionName ~= 'RerollStore',
  'Shrine of Hermes incorrectly reused the WellShop reroll owner')

local surfaceBefore = CurrentRun.NumRerolls
CallFunctionName(surface.Components.RerollButton.OnPressedFunctionName,
  surface, surface.Components.RerollButton)
assert(CurrentRun.NumRerolls == surfaceBefore - 1,
  'Shrine of Hermes reroll did not spend through native AttemptPanelReroll')
assert(CurrentRun.CurrentRoom.Store.StoreOptions[1].Name == 'StoreD'
  and CurrentRun.CurrentRoom.Store.StoreOptions[2].Name == 'StoreE'
  and CurrentRun.CurrentRoom.Store.StoreOptions[3].Name == 'StoreF',
  'Shrine of Hermes reroll did not regenerate the current SurfaceShop offer owner')
assert(surface.Components.RerollButton.Cost == 2,
  'Shrine of Hermes reroll cost did not escalate through native SpentRerolls')

-- Purchased/pending-delivery slots are transaction state, not reroll candidates.
HandleSurfaceShopAction(surface, surface.Components.PurchaseButton1)
assert(CurrentRun.CurrentRoom.Store.StoreOptions[1].Purchased,
  'SurfaceShop purchase fixture did not enter pending-delivery state')
surfaceBefore = CurrentRun.NumRerolls
CallFunctionName(surface.Components.RerollButton.OnPressedFunctionName,
  surface, surface.Components.RerollButton)
assert(CurrentRun.NumRerolls == surfaceBefore - 2,
  'second Shrine of Hermes reroll did not use the escalated native cost')
assert(CurrentRun.CurrentRoom.Store.StoreOptions[1].Name == 'StoreD'
  and CurrentRun.CurrentRoom.Store.StoreOptions[1].Purchased,
  'Shrine of Hermes reroll replaced a purchased/pending-delivery slot')
assert(CurrentRun.CurrentRoom.Store.StoreOptions[2].Name == 'StoreB'
  and CurrentRun.CurrentRoom.Store.StoreOptions[3].Name == 'StoreC',
  'Shrine of Hermes reroll did not replace only the remaining mutable offers')
HandleSurfaceShopAction(surface, surface.Components.PurchaseButton2)
HandleSurfaceShopAction(surface, surface.Components.PurchaseButton3)
assert(not surface.Components.RerollButton.Visible,
  'fully purchased Shrine of Hermes still exposed a spendable reroll')

local beforeSpend = CurrentRun.NumRerolls
CallFunctionName(well.Components.RerollButton.OnPressedFunctionName, well, well.Components.RerollButton)
assert(CurrentRun.NumRerolls == beforeSpend - 1 and storeRerolls == 1,
  'WellShop reroll did not remain owned by native AttemptPanelReroll/RerollStore')
assert(CurrentRun.CurrentRoom.Store.StoreOptions[1].Name == 'StoreD',
  'WellShop native reroll owner did not replace its store options')
assert(well.Components.RerollButton.Cost == 2,
  'WellShop reroll cost did not escalate through native SpentRerolls')

beforeSpend = CurrentRun.NumRerolls
CallFunctionName(sell.Components.RerollButton.OnPressedFunctionName, sell, sell.Components.RerollButton)
assert(CurrentRun.NumRerolls == beforeSpend - 1 and sellRerolls == 1,
  'SellTraits reroll did not remain owned by native AttemptPanelReroll/SellTraitScreenReroll')
assert(CurrentRun.CurrentRoom.SellOptions[3].Name == 'ChoiceD',
  'SellTraits native reroll owner did not regenerate its sell options')
assert(CurrentRun.Hero.Traits[1] == nil,
  'SellTraits reroll performed a sale instead of only regenerating the panel')

-- Empty native owner stays unavailable rather than spending a reroll.
CurrentRun.CurrentRoom.Store.StoreOptions = {}
UpdateStoreReroll(well)
assert(not well.Components.RerollButton.Visible,
  'empty WellShop exposed a fake spendable reroll')

-- Disable must immediately restore native panel capability on current screens.
CurrentRun.CurrentRoom.Store.StoreOptions = { { Name = 'StoreA' } }
CurrentRun.CurrentRoom.SellOptions = { { Name = 'ChoiceA', Value = 100, Rarity = 'Common' } }
UpdateStoreReroll(well)
UpdateStoreReroll(sell, CurrentRun.CurrentRoom.SellOptions, 'SellTraitScreenReroll')
CreateSurfaceShopButtons(surface)
assert(well.Components.RerollButton.Visible and sell.Components.RerollButton.Visible
  and surface.Components.RerollButton.Visible,
  'enabled store owners did not reconcile before disable')
M.dispatch('set_feature', { feature = 'forceEnableRerolls', value = false, includeCatalogs = false })
assert(not well.Components.RerollButton.Visible and not sell.Components.RerollButton.Visible,
  'disabling Force Enable Rerolls left trial-disabled store panels active')
assert(not surface.Components.RerollButton.Visible,
  'disabling Force Enable Rerolls left the injected Shrine of Hermes reroll active')

-- A real native PanelRerollMetaUpgrade must be restored for native Well/Sell,
-- but SurfaceShop has no native reroll baseline to restore.
nativeTraits.PanelRerollMetaUpgrade = true
UpdateStoreReroll(well)
UpdateStoreReroll(sell, CurrentRun.CurrentRoom.SellOptions, 'SellTraitScreenReroll')
assert(well.Components.RerollButton.Visible and sell.Components.RerollButton.Visible,
  'native panel-reroll baseline was not available')
M.dispatch('set_feature', { feature = 'forceEnableRerolls', value = true, includeCatalogs = false })
assert(surface.Components.RerollButton.Visible,
  'Shrine of Hermes did not re-enable with a genuinely owned Panel Reroll Arcana')
M.dispatch('set_feature', { feature = 'forceEnableRerolls', value = false, includeCatalogs = false })
assert(well.Components.RerollButton.Visible and sell.Components.RerollButton.Visible
  and HeroHasTrait('PanelRerollMetaUpgrade'),
  'disable did not restore the actual native store-panel capability')
assert(not surface.Components.RerollButton.Visible,
  'disable fabricated a native Shrine of Hermes reroll baseline')
'''

HARNESS = BASE_HARNESS.replace(
    "print('hades2_force_enable_rerolls_ok')",
    STORE_CASES + "\nprint('hades2_force_enable_rerolls_ok')",
)

with tempfile.TemporaryDirectory(prefix="mgt-force-enable-rerolls-store-panels-") as temporary:
    harness = Path(temporary) / "force-enable-rerolls-store-panels.lua"
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

print("hades2_force_enable_rerolls_store_panels_runtime_ok")
