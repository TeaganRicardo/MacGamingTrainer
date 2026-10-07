from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
lua = (ROOT / "Backend/games/hades2/runtime/hades.lua").read_text(encoding="utf-8")
state = (ROOT / "Sources/Hades2/Hades2BackendState.swift").read_text(encoding="utf-8")
model = (ROOT / "Sources/Hades2/Hades2Model.swift").read_text(encoding="utf-8")

def command_block(name):
    marker = f'if command == "{name}" then'
    start = lua.index(marker)
    tail = lua[start:]
    next_command = tail.find('\n    if command == "', len(marker))
    return tail if next_command < 0 else tail[:next_command]


action = lua[lua.index("local function action("):lua.index("local function editResource")]
sell = command_block("open_sell_traits")
special = command_block("open_special_choice")

# The resident ledger must compare the full semantics of each current one-shot.
assert 'open_special_choice = { "source" }' in lua
assert "actionSemanticKeys" in lua
assert "actionFingerprint" in action
assert "MGT_OUTCOME_UNKNOWN:" in action

# A native modal thread is only accepted at the debugger boundary. The worker
# later records whether the engine-owned modal actually opened or failed.
for block in (sell, special):
    assert 'return nil, "accepted"' in block

assert "result.actionOutcome" in action
assert "lastAction = actionLedger.latestReceipt()" in lua

# The dedup ledger and the projected latest receipt are distinct concerns.
# Sequence contract: modal A accepted -> action B completed -> modal A terminal.
# A's async terminal transition must republish A, rather than requestOrder keeping B.
receipt_projection = lua[lua.index("local function actionReceipt"):lua.index("local function action(")]
assert "M.lastActionReceipt" in receipt_projection
assert "M.requestOrder[#M.requestOrder]" not in receipt_projection
assert "local function publishActionReceipt(record)" in receipt_projection
assert "requestId = requestId" in action
assert "publishActionReceipt(record)" in action

# Hades owns the presentation vocabulary through its typed state boundary.
# Core's generic successful-reply text must be suppressed for modal acknowledgements.
assert "enum Hades2ActionOutcome: String" in state
assert "struct Hades2ActionReceipt" in state
assert "let outcome: Hades2ActionOutcome" in state
assert "let lastAction: Hades2ActionReceipt?" in state
assert 'payload["lastAction"]' in state
modal_model = model[model.index("func openSellTraits()"):model.index("func setMultiplier(", model.index("func openSellTraits()"))]
assert "announceSuccess: false" in modal_model
assert "Hades2Command(rawValue: receipt.command)" in model
assert '"open_sell_traits"' not in model and '"open_special_choice"' not in model
# The model carries language-neutral keys; the module presentation table owns
# the wording in both languages, so a language switch re-renders the receipt.
assert 'presentation("hades2.spawn.purgingPool")' in model
assert 'presentation("hades2.spawn.rewardChoice")' in model
assert "case .accepted:" in model and "hades2.receipt.accepted" in model
assert "case .opened:" in model and "hades2.receipt.opened" in model
assert "case .failed:" in model and "hades2.receipt.failed" in model
assert "receipt.error.map" not in model
assert "hades2.receipt.outcomeUnknown" in model

print("hades2_one_shot_outcomes_ok")
