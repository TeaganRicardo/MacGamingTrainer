"""Rerolls retain native prompt lifetimes and narrative choice draw order.

Engine primitives are temporary in-memory fixtures. The yield/anchor order and
the NPC group override follow the installed 1.143476 native UI owners; this test
does not read an installed game, logs or user saves.
"""
import subprocess
import tempfile
from pathlib import Path

from lua_runtime_support import RESIDENT_DISPATCH_CONTRACT, require_lua52

ROOT = Path(__file__).resolve().parents[1]
LUA = require_lua52("Hades reroll native presentation behavior")
SOURCE = (ROOT / "tests/test_hades2_force_enable_rerolls.py").read_text()
START = SOURCE.index("HARNESS = r'''") + len("HARNESS = r'''")
END = SOURCE.index("dofile(assert(arg[1])); dofile(assert(arg[2]))", START)
BASE = SOURCE[START:END]

PRESENTATION = r'''
local nodes, nextId, refreshes = {}, 1000, 0
local function component(group)
  nextId = nextId + 1
  nodes[nextId] = { Id = nextId, Group = group, alive = true, textAlpha = 1 }
  return nodes[nextId]
end

-- Main.lua's wait, including wait(0), yields to the game coroutine scheduler.
wait = function(duration) coroutine.yield(duration) end
waitUnmodified = wait
thread = function(fn, ...)
  local worker = coroutine.create(fn)
  local ok, message = coroutine.resume(worker, ...)
  assert(ok, message)
  while coroutine.status(worker) ~= 'dead' do
    ok, message = coroutine.resume(worker)
    assert(ok, message)
  end
end
ScreenAnchors.UsePrompts = {}
local function showPrompt(id, target)
  if ScreenAnchors.UsePrompts[id] or next(ActiveScreens) then return end
  local anchor = component('Combat_Menu')
  anchor.Text = target.CanBeRerolled and 'E forward / R reroll 1' or 'E forward'
  ScreenAnchors.UsePrompts[id] = anchor.Id
end
RefreshUseButton = function(id, target)
  local anchor = nodes[ScreenAnchors.UsePrompts[id]]
  if not anchor then return end
  refreshes = refreshes + 1
  ScreenAnchors.UsePrompts[id] = nil
  anchor.textAlpha = 0
  wait(0)
  anchor.alive = false
  showPrompt(id, target)
end
HasHeroTraitValue = function() return nil end
CheckSpecialDoorRequirement = function() return nil end
MapState.OfferedExitDoors, MapState.ShipWheels = {}, {}
AssignRoomToExitDoor = function(door, room)
  door.Room = room
  door.CanBeRerolled = false
  MapState.OfferedExitDoors[door.ObjectId] = door
end
local function promptVisible(id, reroll)
  local anchor = nodes[ScreenAnchors.UsePrompts[id]]
  assert(anchor and anchor.alive and anchor.textAlpha == 1,
    'door instructions disappeared while the native black backing remained')
  assert((anchor.Text:find('R reroll', 1, true) ~= nil) == reroll,
    'door prompt did not reflect the native reroll capability')
  local alive = 0
  for _, node in pairs(nodes) do if node.alive then alive = alive + 1 end end
  assert(alive == 1, 'prompt refresh orphaned a native backing')
end

-- Native CreateUpgradeChoiceButton uses args.ButtonGroupName for purchase,
-- highlight, icon and frame; its ordinary fallback is Combat_Menu. Arachne's
-- original menu instead uses Combat_Menu_Overlay_Backing above narrative art.
local createChoices = CreateBoonLootButtons
CreateBoonLootButtons = function(screen, source, reroll, args)
  createChoices(screen, source, reroll, args)
  for _, button in ipairs(screen.UpgradeButtons) do
    button.Group = args and args.ButtonGroupName or 'Combat_Menu'
    waitUnmodified(.06)
  end
end
OpenUpgradeChoiceMenu = function(source, args)
  args = args or {}
  local screen = {
    Name = 'UpgradeChoice', Source = source, ButtonGroupName = args.ButtonGroupName,
    Components = {
      RerollButton = { Id = 99 }, RerollIcon = { Id = 100 },
      NarrativeBackdrop = { Id = 701, Group = args.ButtonGroupName, Color = 'White', Alpha = .34 },
    },
  }
  ActiveScreens.UpgradeChoice = screen
  ScreenAnchors.ChoiceScreen = screen
  CreateBoonLootButtons(screen, source, false, args)
  return screen
end

dofile(assert(arg[1])); dofile(assert(arg[2]))
local M = __MacGamingTrainerV1
local function enabled(value)
  return M.dispatch('set_feature', {
    feature = 'forceEnableRerolls', value = value, includeCatalogs = false,
  })
end

if arg[3] == 'door' then
  for index, callback in ipairs({ 'AttemptRerollDoor', 'AttemptRerollFieldsDoor', 'AttemptRerollShipWheel' }) do
    enabled(false)
    MapState.OfferedExitDoors, MapState.ShipWheels = {}, {}
    local door = { ObjectId = 800 + index, AllowReroll = true, RerollFunctionName = callback }
    local room = { Name = 'Reward', ChosenRewardType = 'ZeusUpgrade' }
    AssignRoomToExitDoor(door, room)
    if callback == 'AttemptRerollShipWheel' then
      MapState.OfferedExitDoors = {}
      MapState.ShipWheels[door.ObjectId] = door
      door.ChosenRewardType = room.ChosenRewardType
    end
    showPrompt(door.ObjectId, door)
    for _ = 1, 3 do
      enabled(true)
      promptVisible(door.ObjectId, true)
      local anchor = ScreenAnchors.UsePrompts[door.ObjectId]
      local refreshed = refreshes
      for _ = 1, 30 do UpdateTimers(.016) end
      assert(refreshes == refreshed and ScreenAnchors.UsePrompts[door.ObjectId] == anchor,
        'unchanged capability rebuilt the prompt on every frame')
      -- The native action remains the refresh owner after changing the reward.
      thread(function()
        CurrentRun.NumRerolls = CurrentRun.NumRerolls - 1
        room.ChosenRewardType = 'PoseidonUpgrade'
        RefreshUseButton(door.ObjectId, door)
      end)
      UpdateTimers(.016)
      promptVisible(door.ObjectId, true)
      enabled(false)
      promptVisible(door.ObjectId, false)
    end
    nodes[ScreenAnchors.UsePrompts[door.ObjectId]].alive = false
    ScreenAnchors.UsePrompts[door.ObjectId] = nil
  end
else
  enabled(true)
  local source = copy(EnemyData.NPC_Arachne_01)
  source.ObjectId, source.BlockReroll = 802, true
  source.UpgradeOptions = { copy(basePool[1]), copy(basePool[2]), copy(basePool[3]) }
  local screen
  thread(function()
    screen = OpenUpgradeChoiceMenu(source, { ButtonGroupName = 'Combat_Menu_Overlay_Backing' })
  end)
  local backdrop = screen.Components.NarrativeBackdrop
  for _ = 1, 3 do
    local before = table.concat({source.UpgradeOptions[1].ItemName,
      source.UpgradeOptions[2].ItemName, source.UpgradeOptions[3].ItemName}, ':')
    local currency = CurrentRun.NumRerolls
    thread(AttemptPanelReroll, screen, screen.Components.RerollButton)
    local after = table.concat({source.UpgradeOptions[1].ItemName,
      source.UpgradeOptions[2].ItemName, source.UpgradeOptions[3].ItemName}, ':')
    assert(before ~= after and CurrentRun.NumRerolls < currency,
      'NPC redraw lost changed choices or native spend')
    assert(screen.Components.NarrativeBackdrop == backdrop and backdrop.Id == 701
      and backdrop.Color == 'White' and backdrop.Alpha == .34,
      'NPC reroll replaced or recolored its narrative background')
    for _, button in ipairs(screen.UpgradeButtons) do
      assert(button.Group == screen.ButtonGroupName,
        'Arachne choices moved behind the narrative decoration and white dim layer')
    end
    local status = M.dispatch('status', { includeCatalogs = false })
    assert(not status.runtimeOutcomeUnknown and status.activeFeatures.forceEnableRerolls,
      'completed NPC redraw closed native operation trust')
  end
end
print(arg[3] .. '_reroll_presentation_ok')
'''

with tempfile.TemporaryDirectory(prefix="mgt-reroll-presentation-") as temporary:
    fixture = Path(temporary) / "presentation.lua"
    fixture.write_text(BASE + PRESENTATION, encoding="utf-8")
    for case in ("door", "npc"):
        completed = subprocess.run(
            [LUA, str(fixture), str(ROOT / "Backend/games/hades2/runtime/hades.lua"),
             str(RESIDENT_DISPATCH_CONTRACT), case], capture_output=True, text=True,
        )
        assert completed.returncode == 0, completed.stdout + completed.stderr
        assert case + "_reroll_presentation_ok" in completed.stdout

print("hades2_reroll_presentation_ok")
