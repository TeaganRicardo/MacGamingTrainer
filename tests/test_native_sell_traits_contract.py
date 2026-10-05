from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
model = (ROOT / "Sources/Hades2/Hades2Model.swift").read_text()
view = (ROOT / "Sources/Hades2/Hades2View.swift").read_text()
adapter = (ROOT / "Backend/games/hades2/adapter.py").read_text()
lua = (ROOT / "Backend/games/hades2/runtime/hades.lua").read_text()

assert "'open_sell_traits'" not in adapter[adapter.index('def _replay_preferences'):adapter.index('def scan(', adapter.index('def _replay_preferences'))]

def command_block(name):
    marker = f'if command == "{name}" then'
    start = lua.index(marker)
    tail = lua[start:]
    next_command = tail.find('\n    if command == "', len(marker))
    return tail if next_command < 0 else tail[:next_command]


block = command_block("open_sell_traits")
for token in (
    'sceneName() ~= "run"',
    'AreScreensActive',
    'OpenSellTraitMenu',
    'DeepCopyTable(ScreenData.SellTraits)',
    'MacGamingTrainerCloseSellTraitScreen',
    'ScreenData.SellTraits = trainerScreen',
    'ScreenData.SellTraits = originalScreen',
    'thread(runSell)',
):
    assert token in block, token
assert 'thread(OpenSellTraitMenu' not in block, "sell UI must stay wrapped until its temporary screen definition is restored"
assert 'OpenSellTraitMenu({})' not in block, "native sell UI must not block the LLDB dispatch synchronously"
assert 'return actionLedger.run(command, params' in block

close_block = lua[lua.index('function MacGamingTrainerCloseSellTraitScreen'):lua.index('if command == "open_sell_traits" then')]
assert 'CloseStoreScreen(screen, button)' in close_block
assert 'CurrentRun.CurrentRoom.Store.StoreOptions' in close_block
assert 'PurchaseButton' in close_block
assert 'UseableOff({ Ids = purchaseIds })' in close_block
assert 'AltAspectRatioFramesHide()' in close_block
assert 'OnScreenCloseStarted(screen)' in close_block
assert 'CloseScreen(GetAllIds(screen.Components), 0.15)' in close_block
assert 'OnScreenCloseFinished(screen)' in close_block
assert 'ShowCombatUI(screen.Name)' in close_block
assert 'SetPlayerVulnerable(screen.Name)' in close_block
assert 'CurrentRun.CurrentRoom.Store =' not in close_block, "trainer must never fabricate Store state"

assert 'func openSellTraits()' in model
assert '.openSellTraits' in model
# Player-facing copy resolves through the module presentation table, so the view
# names a key rather than embedding the official term.
assert 'Label(text("hades2.spawn.purgingPool")' in view
assert 'text("hades2.spawn.open")' in view
assert '出售祝福' not in view
assert 'model.openSellTraits()' in view

print("native_sell_traits_contract_ok")
