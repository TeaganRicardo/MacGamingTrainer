"""Single-source Hades II error-registry contract for issue #204."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from core.adapter import AdapterError
from games.hades2 import error_presentation
from games.hades2 import runtime_error_presentation

RUNTIME_SOURCE = (ROOT / "Backend/games/hades2/runtime_error_presentation.py").read_text(encoding="utf-8")
LUA = (ROOT / "Backend/games/hades2/runtime/hades.lua").read_text(encoding="utf-8")

# Runtime mappings must be derived from the declarative registry rather than
# mirrored in a second module.
for forbidden in ("_RUNTIME_KEYS", "_COMPOSED_PREFIXES", "_SHARED_COMPOSED", "_FALLBACK_KEY"):
    assert forbidden not in RUNTIME_SOURCE, f"runtime error mapping mirror survived: {forbidden}"

runtime_rules = [rule for rule in error_presentation.REGISTRY if rule.get("runtime")]
assert runtime_rules, "the registry declares no runtime refusals"
assert getattr(error_presentation, "RUNTIME_FALLBACK_KEY", None) == "hades2.error.runtimeActionFailed"

# Every runtime entry carries its scope and producer provenance. This is the
# reverse half of coverage: a dead registry entry must fail even if no caller
# happens to probe it.
def function_block(name):
    # Match the function name exactly: "action" must not bind the earlier
    # actionFingerprint/actionReceipt helpers.
    marker = f"local function {name}("
    start = LUA.find(marker)
    assert start >= 0, f"missing Lua helper producer {name}"
    end = LUA.find("\n  local function ", start + len(marker))
    return LUA[start:] if end < 0 else LUA[start:end]


def command_block(name):
    marker = f'if command == "{name}" then'
    start = LUA.find(marker)
    assert start >= 0, f"missing Lua command producer {name}"
    end = LUA.find('\n    if command == "', start + len(marker))
    return LUA[start:] if end < 0 else LUA[start:end]


for rule in runtime_rules:
    runtime = rule["runtime"]
    commands = runtime.get("commands")
    producer = runtime.get("producer")
    assert commands == "*" or (
        isinstance(commands, (list, tuple)) and commands and all(isinstance(value, str) and value for value in commands)
    ), rule
    assert isinstance(producer, dict), rule
    kind, name = producer.get("kind"), producer.get("name")
    assert kind in {"command", "helper"} and isinstance(name, str) and name, rule
    block = command_block(name) if kind == "command" else function_block(name)
    if rule["match"] == "literal":
        assert rule["message"] in block, f"dead runtime literal: {rule}"
    elif rule["match"] == "prefix":
        assert rule["prefix"] in block, f"dead runtime prefix: {rule}"
    elif rule["match"] == "regex":
        # The only shared dynamic helper composes Unsupported <purpose>: missing
        # <function>. Assert both static source fragments exist in the declared
        # producer rather than pretending the regex itself is Lua source.
        assert "Unsupported " in block and ": missing " in block, f"dead runtime regex: {rule}"
    else:
        raise AssertionError(f"unsupported runtime registry shape: {rule['match']}")

# Behaviour snapshot from the pre-#204 funnel. The refactor may change the
# registration site, not the key/argument result.
CASES = (
    ("open_sell_traits", "Cannot open boon sell screen while another screen is active", "hades2.error.sellScreenBusy", ()),
    ("open_sell_traits", "Boon selling requires an active run room", "hades2.error.sellNeedsRunRoom", ()),
    ("open_sell_traits", "Native boon sell screen data is unavailable", "hades2.error.sellDataUnavailable", ()),
    ("open_special_choice", "Cannot open special blessing choice while another screen is active", "hades2.error.choiceScreenBusy", ()),
    ("open_special_choice", "Cannot open special blessing choice during a transition", "hades2.error.choiceDuringTransition", ()),
    ("open_special_choice", "Special blessing choice requires an active run room", "hades2.error.choiceNeedsRunRoom", ()),
    ("open_special_choice", "Special blessing source has no audited native choice flow", "hades2.error.choiceNoAuditedFlow", ()),
    ("open_special_choice", "Special blessing source data is unavailable", "hades2.error.choiceSourceUnavailable", ()),
    ("open_special_choice", "Special blessing choice data is unavailable", "hades2.error.choiceDataUnavailable", ()),
    ("open_special_choice", "No eligible special blessings are available", "hades2.error.noEligibleSpecialRewards", ()),
    ("open_special_choice", "Unsupported native special blessing choice: missing OpenUpgradeChoiceMenu", "hades2.error.nativeFunctionMissing", ("native special blessing choice", "OpenUpgradeChoiceMenu")),
    ("spawn_reward", "Selected boon is already owned", "hades2.error.exactAlreadyOwned", ()),
    ("spawn_reward", "Selected boon is not currently eligible", "hades2.error.exactNotEligible", ()),
    ("spawn_reward", "Selected boon became unavailable before acquisition", "hades2.error.exactNotEligible", ()),
    ("set_trait_level", "Trait mutation requires an active run room", "hades2.error.traitMutationNeedsRun", ()),
    ("set_trait_level", "Trait selection belongs to a stale runtime generation", "hades2.error.traitSelectionStale", ()),
    ("set_trait_level", "Trait instance is no longer present", "hades2.error.traitTargetMissing", ()),
    ("set_trait_level", "Trait target changed since selection", "hades2.error.traitTargetChanged", ()),
    ("set_trait_level", "Trait level editing is unavailable for the selected target", "hades2.error.traitLevelUnavailable", ()),
    ("set_trait_level", "Trait target level must be higher than the current level", "hades2.error.traitLevelTargetInvalid", ()),
    ("set_trait_level", "Trait is no longer eligible for a meaningful level increase", "hades2.error.traitLevelNoLongerEligible", ()),
    ("set_trait_level", "Trait level increase did not reach the requested target level", "hades2.error.traitLevelNoEffect", ()),
    ("set_trait_rarity", "Trait rarity editing is unavailable for the selected target", "hades2.error.traitRarityUnavailable", ()),
    ("set_trait_rarity", "Trait rarity recompute did not reach the requested rarity", "hades2.error.traitRarityNoEffect", ()),
    ("remove_trait", "Trait removal is unavailable for the selected target", "hades2.error.traitRemovalUnavailable", ()),
    ("remove_trait", "Trait removal capability is unknown", "hades2.error.traitRemovalCapabilityUnknown", ()),
    ("remove_trait", "Native trait removal left a matching instance mounted", "hades2.error.traitRemovalNoEffect", ()),
    ("remove_trait", "Direct trait removal left the selected instance mounted", "hades2.error.traitRemovalNoEffect", ()),
    ("remove_trait", "Action requires a requestId of 1..128 characters", "hades2.error.requestIdRequired", ()),
    ("remove_trait", "requestId reused for a different action", "hades2.error.requestIdReused", ()),
    ("remove_trait", "MGT_OUTCOME_UNKNOWN: Previous action outcome is unknown; do not retry", "hades2.error.outcomeUnknownRuntime", ()),
)


for command, detail, expected_key, expected_arguments in CASES:
    raw = f'[string "mgt"]:123: {detail}'
    error = AdapterError("lua_error", raw, diagnostic=raw)
    presented = runtime_error_presentation.present_runtime_error(command, error)
    assert presented.code == "lua_error", (command, detail, presented.code)
    assert presented.presentation == expected_key, (command, detail, presented.presentation)
    assert tuple(presented.arguments) == expected_arguments, (command, detail, presented.arguments)

# Unknown runtime detail remains the same generic fallback.
unknown = AdapterError("lua_error", "totally unknown runtime failure")
presented = runtime_error_presentation.present_runtime_error("remove_trait", unknown)
assert presented.code == "lua_error"
assert presented.presentation == error_presentation.RUNTIME_FALLBACK_KEY
assert tuple(presented.arguments) == ()

print("hades2_error_registry_single_source_ok")
