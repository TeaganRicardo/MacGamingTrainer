import subprocess
import tempfile
from pathlib import Path

from lua_runtime_support import RESIDENT_DISPATCH_CONTRACT, require_lua52

ROOT = Path(__file__).resolve().parents[1]
LUA = require_lua52("Force Enable Rerolls Selene behavior")

SOURCE = (ROOT / "tests/test_hades2_force_enable_rerolls.py").read_text()
START = SOURCE.index("HARNESS = r'''") + len("HARNESS = r'''")
END = SOURCE.index("\n'''\n\nwith tempfile", START)
BASE_HARNESS = SOURCE[START:END]

SELENE_CASES = r'''
-- Selene screens are not UpgradeChoice owners, but Force Enable Rerolls must
-- still expose a Hades-native contextual reroll that delegates spend/input/RNG
-- to AttemptPanelReroll and mutates the current owner in place.

local nextComponentId = 700
local function component()
  nextComponentId = nextComponentId + 1
  return { Id = nextComponentId, Visible = false }
end

CreateScreenComponent = function(args)
  local value = component()
  value.Name = args.Name
  value.Group = args.Group
  return value
end
CreateTextBox = function() end
Destroy = function() end
SetAnimation = function() end
UpdateAdditionalTalentPointButton = function() end
IsEmpty = function(value) return type(value) ~= 'table' or next(value) == nil end

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
ScreenData.SpellScreen = {
  ComponentData = {
    ActionBar = {
      ChildrenOrder = { 'SelectButton' },
      Children = { SelectButton = {} },
    },
  },
}
ScreenData.TalentScreen = {
  ComponentData = {
    ActionBar = {
      ChildrenOrder = { 'CloseButton', 'SelectButton' },
      Children = { CloseButton = {}, SelectButton = {} },
    },
  },
}

SpellData = {
  SpellA = { Name = 'SpellA', TraitName = 'SpellATrait', Talents = { Legendary = {} } },
  SpellB = { Name = 'SpellB', TraitName = 'SpellBTrait', Talents = { Legendary = {} } },
  SpellC = { Name = 'SpellC', TraitName = 'SpellCTrait', Talents = { Legendary = {} } },
  SpellD = { Name = 'SpellD', TraitName = 'SpellDTrait', Talents = { Legendary = {} } },
}
for _, spell in pairs(SpellData) do
  TraitData[spell.TraitName] = { Name = spell.TraitName }
end
SpellTalentData = { ServeDuoGameRequirements = {}, InitialBonuses = {} }
GameState.TraitsTaken = {}
SessionMapState.SelectedSpells = {}
SessionMapState.DuoTalentEligibleSpell = {}
SessionMapState.DuoTalentEligibleGender = {}

GetEligibleSpells = function(screen)
  if not IsEmpty(SessionMapState.SelectedSpells) then
    return SessionMapState.SelectedSpells
  end
  local result = {}
  for name in pairs(SpellData) do result[#result + 1] = name end
  table.sort(result)
  return result
end

local function mountInjectedRerollComponents(screen, screenName)
  local data = ScreenData[screenName].ComponentData
  if data.RerollIcon then screen.Components.RerollIcon = component() end
  if data.ActionBar and data.ActionBar.Children and data.ActionBar.Children.RerollButton then
    screen.Components.RerollButton = component()
  end
end

CreateSpellButtons = function(screen)
  for index = 1, 3 do
    screen.Components['PurchaseButton'..index] = nil
  end
  local eligible = GetEligibleSpells(screen)
  local index = 1
  while index <= 3 and #eligible > 0 do
    local name = RemoveRandomValue(eligible)
    local button = component()
    button.Screen = screen
    button.SpellName = name
    button.TraitName = SpellData[name].TraitName
    button.OnPressedFunctionName = 'AcceptAndCloseSpellScreen'
    screen.Components['PurchaseButton'..index] = button
    index = index + 1
  end
end

local spellAcquireCount = 0
AcceptAndCloseSpellScreen = function(screen, button)
  spellAcquireCount = spellAcquireCount + 1
  CurrentRun.Hero.SlottedSpell = copy(SpellData[button.SpellName])
end

OpenSpellScreen = function(source)
  local screen = {
    Name = 'SpellScreen', Source = source, StripRequirements = false,
    Components = {}, KeepOpen = true,
  }
  ActiveScreens.SpellScreen = screen
  mountInjectedRerollComponents(screen, 'SpellScreen')
  CreateSpellButtons(screen)
  return screen
end

local treeGeneration = 0
CreateTalentTree = function()
  treeGeneration = treeGeneration + 1
  local mutableName = treeGeneration % 2 == 1 and 'TalentNewA' or 'TalentNewB'
  return {
    {
      [1] = { Name = 'TalentGeneratedFixed', Rarity = 'Rare', LinkTo = { 1, 2 } },
    },
    {
      [1] = { Name = mutableName, Rarity = 'Epic', LinkFrom = { 1 } },
      [2] = { Name = 'TalentGeneratedQueued', Rarity = 'Rare', LinkFrom = { 1 } },
    },
  }
end
for _, name in ipairs({
  'TalentFixed', 'TalentOld', 'TalentQueued', 'TalentGeneratedFixed',
  'TalentGeneratedQueued', 'TalentNewA', 'TalentNewB',
}) do
  TraitData[name] = { Name = name }
end

CreateTalentTreeIcons = function(screen)
  screen.Components.TalentIds = {}
  screen.Components.TalentFrameIds = {}
  screen.Components.LinkObjects = {}
  for depth, column in ipairs(CurrentRun.Hero.SlottedSpell.Talents or {}) do
    for slot, node in pairs(column) do
      local object = component()
      object.Data = node
      object.TalentColumn = depth
      object.TalentRow = slot
      screen.Components['TalentObject'..depth..'_'..slot] = object
      screen.Components.TalentIds[#screen.Components.TalentIds + 1] = object.Id
    end
  end
end
UpdateTalentButtons = function(screen)
  screen.AllInvested = true
  for _, column in ipairs(CurrentRun.Hero.SlottedSpell.Talents or {}) do
    for _, node in pairs(column) do
      if not node.Invested and not node.QueuedInvested then screen.AllInvested = false end
    end
  end
end

local talentOpenCount = 0
OpenTalentScreen = function(source, readOnly)
  talentOpenCount = talentOpenCount + 1
  local screen = {
    Name = 'TalentScreen', Source = source, ReadOnly = readOnly,
    Components = {}, KeepOpen = true, StartingTalentPoints = CurrentRun.NumTalentPoints,
    QueuedTalents = {},
  }
  ActiveScreens.TalentScreen = screen
  mountInjectedRerollComponents(screen, 'TalentScreen')
  CreateTalentTreeIcons(screen)
  UpdateTalentButtons(screen)
  return screen
end

M.dispatch('set_feature', { feature = 'forceEnableRerolls', value = true, includeCatalogs = false })
CurrentRun.NumRerolls = 6
CurrentRun.CurrentRoom.SpentRerolls = {}
CurrentRun.Hero.SlottedSpell = nil
SessionMapState.SelectedSpells = { 'SpellA', 'SpellB', 'SpellC' }
local spellSource = { Name = 'SpellDrop', ObjectId = 501 }
local spellScreen = OpenSpellScreen(spellSource)
assert(type(spellScreen.Components.RerollButton) == 'table'
  and spellScreen.Components.RerollButton.Visible
  and spellScreen.Components.RerollButton.OnPressedFunctionName == 'AttemptPanelReroll',
  'Force Enable Rerolls did not expose the native-style reroll action on SpellScreen')
local beforeSpells = {}
for index = 1, 3 do
  beforeSpells[spellScreen.Components['PurchaseButton'..index].SpellName] = true
end
CallFunctionName(spellScreen.Components.RerollButton.OnPressedFunctionName,
  spellScreen, spellScreen.Components.RerollButton)
local changedSpell = false
for index = 1, 3 do
  local button = spellScreen.Components['PurchaseButton'..index]
  assert(type(button) == 'table' and SpellData[button.SpellName],
    'SpellScreen reroll produced an invalid spell candidate')
  if not beforeSpells[button.SpellName] then changedSpell = true end
end
assert(changedSpell, 'SpellScreen reroll did not produce a genuinely changed eligible set')
assert(CurrentRun.NumRerolls == 5, 'SpellScreen reroll did not spend through AttemptPanelReroll')
assert(CurrentRun.Hero.SlottedSpell == nil and spellAcquireCount == 0,
  'SpellScreen reroll acquired a Hex instead of only regenerating the open menu')

-- With no fourth eligible spell, a three-choice screen has no changed set and
-- must not expose a fake spendable reroll.
local savedSpellD = SpellData.SpellD
SpellData.SpellD = nil
SessionMapState.SelectedSpells = { 'SpellA', 'SpellB', 'SpellC' }
local exhaustedSpell = OpenSpellScreen({ Name = 'SpellDrop', ObjectId = 502 })
assert(not exhaustedSpell.Components.RerollButton.Visible,
  'SpellScreen exposed reroll with no changed eligible set')
SpellData.SpellD = savedSpellD

local fixedNode = { Name = 'TalentFixed', Rarity = 'Rare', Invested = true, LinkTo = { 1, 2 } }
local mutableNode = { Name = 'TalentOld', Rarity = 'Common', LinkFrom = { 1 } }
local queuedNode = { Name = 'TalentQueued', Rarity = 'Rare', QueuedInvested = true, LinkFrom = { 1 } }
CurrentRun.Hero.SlottedSpell = {
  Name = 'SpellA', TraitName = 'SpellATrait',
  Talents = { { [1] = fixedNode }, { [1] = mutableNode, [2] = queuedNode } },
}
CurrentRun.NumTalentPoints = 2
CurrentRun.NumRerolls = 5
CurrentRun.CurrentRoom.SpentRerolls = {}
local talentSource = { Name = 'TalentDrop', ObjectId = 601 }
local talentScreen = OpenTalentScreen(talentSource, false)
talentScreen.QueuedTalents = { queuedNode }
talentScreen.SelectedTalent = queuedNode
assert(talentScreen.Components.RerollButton.Visible,
  'Force Enable Rerolls did not expose the native-style reroll action on writable TalentScreen')
local startingPoints = CurrentRun.NumTalentPoints
local startingScreenPoints = talentScreen.StartingTalentPoints
local startingOpenCount = talentOpenCount
CallFunctionName(talentScreen.Components.RerollButton.OnPressedFunctionName,
  talentScreen, talentScreen.Components.RerollButton)
assert(CurrentRun.NumRerolls == 4, 'TalentScreen reroll did not spend through AttemptPanelReroll')
assert(CurrentRun.NumTalentPoints == startingPoints and talentScreen.StartingTalentPoints == startingScreenPoints,
  'TalentScreen reroll changed available or starting talent points')
assert(talentOpenCount == startingOpenCount,
  'TalentScreen reroll reopened the owner and repeated pickup/point side effects')
assert(CurrentRun.Hero.SlottedSpell.Talents[1][1] == fixedNode and fixedNode.Name == 'TalentFixed'
  and fixedNode.Invested,
  'TalentScreen reroll replaced an invested Path of Stars node')
assert(CurrentRun.Hero.SlottedSpell.Talents[2][2] == queuedNode
  and queuedNode.Name == 'TalentQueued' and queuedNode.QueuedInvested
  and talentScreen.QueuedTalents[1] == queuedNode,
  'TalentScreen reroll replaced or detached a queued Path of Stars node')
assert(mutableNode.Name ~= 'TalentOld',
  'TalentScreen reroll did not regenerate an uninvested Path of Stars node')
assert(talentScreen.Components.TalentObject2_1.Data == mutableNode
  and talentScreen.Components.TalentObject2_1.Data.Name == mutableNode.Name,
  'TalentScreen UI no longer points at the regenerated owner node')

local readOnly = OpenTalentScreen({ Name = 'TalentDrop', ObjectId = 602 }, true)
assert(not readOnly.Components.RerollButton.Visible,
  'read-only TalentScreen exposed a spendable reroll action')

M.dispatch('set_feature', { feature = 'forceEnableRerolls', value = false, includeCatalogs = false })
assert(not spellScreen.Components.RerollButton.Visible and not talentScreen.Components.RerollButton.Visible,
  'disabling Force Enable Rerolls left Selene reroll actions visible')
'''

HARNESS = BASE_HARNESS.replace(
    "print('hades2_force_enable_rerolls_ok')",
    SELENE_CASES + "\nprint('hades2_force_enable_rerolls_ok')",
)

with tempfile.TemporaryDirectory(prefix="mgt-force-enable-rerolls-selene-") as temporary:
    harness = Path(temporary) / "force-enable-rerolls-selene.lua"
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

print("hades2_force_enable_rerolls_selene_runtime_ok")
