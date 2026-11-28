"""Hades II runtime and backend errors map to presentation keys and arguments (#204).

An error message that maps to no key reaches the player as raw Chinese text.
"""
import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from core.adapter import AdapterError
from core.errors import PresentableError
from games.hades2 import error_presentation
from games.hades2 import runtime_error_presentation

# Runtime refusals, as the resident raises them, map to these keys.
CASES = (
    ("open_sell_traits", "Cannot open boon sell screen while another screen is active", "hades2.error.sellScreenBusy", ()),
    ("open_sell_traits", "Boon selling requires a live trait owner", "hades2.error.sellNeedsTraitOwner", ()),
    ("open_sell_traits", "Native boon sell screen data is unavailable", "hades2.error.sellDataUnavailable", ()),
    ("open_special_choice", "Cannot open special blessing choice while another screen is active", "hades2.error.choiceScreenBusy", ()),
    ("open_special_choice", "Cannot open special blessing choice during a transition", "hades2.error.choiceDuringTransition", ()),
    ("open_special_choice", "Special blessing choice requires a live Hero/run owner", "hades2.error.choiceNeedsHeroOwner", ()),
    ("open_special_choice", "Special blessing source has no audited native choice flow", "hades2.error.choiceNoAuditedFlow", ()),
    ("open_special_choice", "Special blessing source data is unavailable", "hades2.error.choiceSourceUnavailable", ()),
    ("open_special_choice", "Special blessing choice data is unavailable", "hades2.error.choiceDataUnavailable", ()),
    ("open_special_choice", "No eligible special blessings are available", "hades2.error.noEligibleSpecialRewards", ()),
    ("open_special_choice", "Unsupported native special blessing choice: missing OpenUpgradeChoiceMenu", "hades2.error.nativeFunctionMissing", ("native special blessing choice", "OpenUpgradeChoiceMenu")),
    ("spawn_reward", "Selected boon is already owned", "hades2.error.exactAlreadyOwned", ()),
    ("spawn_reward", "Selected boon is not currently eligible", "hades2.error.exactNotEligible", ()),
    ("spawn_reward", "Selected boon does not support the requested rarity", "hades2.error.exactRarityUnsupported", ()),
    ("acquire_chaos_pair", "Selected boon does not support the requested level", "hades2.error.exactLevelUnsupported", ()),
    ("spawn_reward", "Echo previous-run boon is no longer eligible", "hades2.error.exactNotEligible", ()),
    ("spawn_reward", "Echo previous-run boon acquisition failed", "hades2.error.echoLastRunFailed", ()),
    ("set_trait_level", "Trait mutation requires a live trait owner", "hades2.error.traitMutationNeedsOwner", ()),
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
    ("remove_trait", "Direct trait removal left the selected instance mounted", "hades2.error.traitRemovalNoEffect", ()),
    ("set_trait_remaining_uses", "Temporary effect duration editing is unavailable for the selected target", "hades2.error.traitDurationUnavailable", ()),
    ("set_trait_remaining_uses", "Temporary effect duration did not reach the requested remaining uses", "hades2.error.traitDurationNoEffect", ()),
    ("expire_trait", "Temporary effect duration did not reach the requested remaining uses", "hades2.error.traitDurationNoEffect", ()),
    ("expire_trait", "Temporary effect expiry is unavailable for the selected target", "hades2.error.traitExpiryUnavailable", ()),
    ("expire_trait", "Temporary effect expiry left the selected instance mounted", "hades2.error.traitRemovalNoEffect", ()),
    ("remove_trait", "Temporary effect cancellation left the selected instance mounted", "hades2.error.traitRemovalNoEffect", ()),
    ("set_trait_level", "Chaos trait editing is unavailable", "hades2.error.chaosTraitEditUnavailable", ()),
    ("set_trait_rarity", "Chaos trait edit failed", "hades2.error.chaosTraitEditFailed", ()),
    ("advance_trait_lifecycle", "Chaos lifecycle transition is unavailable", "hades2.error.chaosLifecycleUnavailable", ()),
    ("advance_trait_lifecycle", "Chaos lifecycle transition failed", "hades2.error.chaosLifecycleFailed", ()),
    ("spawn_reward", "Chaos exact acquisition is unavailable", "hades2.error.chaosExactUnavailable", ()),
    ("spawn_reward", "Chaos exact acquisition failed", "hades2.error.chaosExactFailed", ()),
    ("acquire_chaos_pair", "Chaos encounter count must be a whole number from 1 to 100", "hades2.error.chaosEncountersRange", ()),
    ("spawn_reward", "Selene spell target is unavailable", "hades2.error.exactNotEligible", ()),
    ("spawn_reward", "Selene talent is unavailable for the current Path of Stars", "hades2.error.exactNotEligible", ()),
    ("spawn_reward", "Selene talent is no longer available in the current Path of Stars", "hades2.error.exactNotEligible", ()),
    ("spawn_reward", "Mounted Selene talent is unavailable", "hades2.error.exactNotEligible", ()),
    ("spawn_reward", "Selene spell acquisition failed", "hades2.error.seleneExactFailed", ()),
    ("spawn_reward", "Selene talent acquisition failed", "hades2.error.seleneExactFailed", ()),
    ("set_trait_level", "Not enough uninvested Path of Stars nodes remain for the requested level", "hades2.error.traitLevelNoLongerEligible", ()),
    ("set_trait_level", "Selene talent tree changed before the requested level was applied", "hades2.error.traitTargetChanged", ()),
    ("remove_trait", "Selene spell removal left owner state mounted", "hades2.error.traitRemovalNoEffect", ()),
    ("remove_trait", "Selene talent removal left the mounted effect present", "hades2.error.traitRemovalNoEffect", ()),
    ("spawn_reward", "Exact costume target is unavailable", "hades2.error.exactNotEligible", ()),
    ("spawn_reward", "Arachne costume acquisition failed", "hades2.error.costumeOwnerFailed", ()),
    ("spawn_reward", "Arachne costume replacement left previous owner mounted", "hades2.error.costumeOwnerFailed", ()),
    ("remove_trait", "Arachne costume removal left owner state mounted", "hades2.error.traitRemovalNoEffect", ()),
    ("remove_trait", "Action requires a requestId of 1..128 characters", "hades2.error.requestIdRequired", ()),
    ("remove_trait", "requestId reused for a different action", "hades2.error.requestIdReused", ()),
    ("remove_trait", "MGT_OUTCOME_UNKNOWN: Previous action outcome is unknown; do not retry", "hades2.error.outcomeUnknownRuntime", ()),
    ("apply_world_occurrence", "Unsupported next occurrence target", "hades2.error.invalidNextOccurrence", ()),
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

# The registry is strictly for resident-Lua runtime messages; Python raise sites
# carry typed PresentableError keys directly.
assert not hasattr(error_presentation, "presentation_for")
assert all(isinstance(rule.get("runtime"), dict) for rule in error_presentation.REGISTRY)

# The registry itself has no duplicate, invalid or shadowed rule; a shadowed
# rule silently sends a player's error to the wrong key.
assert not error_presentation.check_registry(), error_presentation.check_registry()
assert not error_presentation._unreachable(error_presentation.REGISTRY)

# Every player-facing raise site in Hades II carries a valid key whose
# placeholder count matches its arguments, and zero raw CJK prose raises exist.
EN = json.loads((ROOT / "Sources/Hades2/Presentation/Localization/hades2.en.json").read_text(encoding="utf-8"))["entries"]
HOST_EN = {
    match.group(1): match.group(2)
    for raw in (ROOT / "Resources/Localization/en.lproj/Host.strings").read_text(encoding="utf-8").splitlines()
    for match in (re.fullmatch(r'"([^"]+)"\s*=\s*"(.*)";', raw.strip()),)
    if match
}
CJK = re.compile(r"[㐀-鿿]")
BOUNDARY_DAMAGE = re.compile(r"[　-〿＀-￯]")

_TYPED_ERROR_NAMES = frozenset({
    "Hades2PresentationError",
    "Hades2ValueError",
    "Hades2RuntimeError",
    "SaveBatchValidationError",
    "SaveEquipmentBatchValidationError",
    "_SaveEditorActionValidationError",
    "PersistenceError",
    "ResidentSessionError",
    "ResidentConnectionError",
    "TransportError",
    "AdapterError",
    "HostPresentationError",
})

def _call_name(call: ast.Call) -> str:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return ""

def _string_constants(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.IfExp):
        return _string_constants(node.body) + _string_constants(node.orelse)
    return []

def _kwarg(call: ast.Call, name: str):
    return next((kw.value for kw in call.keywords if kw.arg == name), None)

def _key_and_args(call: ast.Call, fn: str):
    if fn in ("Hades2ValueError", "Hades2RuntimeError"):
        key_node = call.args[0] if call.args else _kwarg(call, "key")
        args_node = call.args[2] if len(call.args) > 2 else _kwarg(call, "arguments")
        return key_node, args_node, True
    if fn in ("SaveBatchValidationError", "SaveEquipmentBatchValidationError"):
        key_node = call.args[0] if call.args else _kwarg(call, "key")
        return key_node, None, False
    if fn in ("Hades2PresentationError", "_SaveEditorActionValidationError"):
        key_node = call.args[1] if len(call.args) > 1 else _kwarg(call, "presentation")
        args_node = call.args[2] if len(call.args) > 2 else _kwarg(call, "arguments")
        return key_node, args_node, True
    if fn == "PersistenceError":
        key_node = _kwarg(call, "presentation")
        args_node = _kwarg(call, "arguments")
        return key_node, args_node, True
    # AdapterError / TransportError / HostPresentationError / ResidentSessionError / ResidentConnectionError
    key_node = call.args[1] if len(call.args) > 1 else _kwarg(call, "presentation")
    args_node = _kwarg(call, "arguments")
    return key_node, args_node, True

raw_cjk_raises = []
bad_typed_keys = []
for path in sorted((ROOT / "Backend/games/hades2").glob("*.py")):
    if path.name == "error_presentation.py":
        continue
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
            if _call_name(node.exc) in ("ValueError", "RuntimeError"):
                text = ast.unparse(node.exc)
                if CJK.search(text):
                    raw_cjk_raises.append(f"{path.name}:{node.lineno}: {text}")
            continue
        if not isinstance(node, ast.Call):
            continue
        fn = _call_name(node)
        if fn not in _TYPED_ERROR_NAMES:
            continue
        key_node, args_node, check_arg_count = _key_and_args(node, fn)
        for key in _string_constants(key_node):
            if CJK.search(key):
                raw_cjk_raises.append(f"{path.name}:{node.lineno}: {key!r}")
                continue
            if not key.startswith(("hades2.", "host.")):
                continue
            table = HOST_EN if key.startswith("host.") else EN
            template = table.get(key)
            if template is None:
                bad_typed_keys.append(f"{path.name}:{node.lineno}: missing key {key}")
                continue
            if not check_arg_count:
                continue
            needed = len(set(re.findall(r"\{(\d+)\}", template)))
            if isinstance(args_node, (ast.Tuple, ast.List)):
                if len(args_node.elts) != needed:
                    bad_typed_keys.append(
                        f"{path.name}:{node.lineno}: {key} expects {needed} args, got {len(args_node.elts)}"
                    )
                for elt in args_node.elts:
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                        if CJK.search(elt.value) or BOUNDARY_DAMAGE.search(elt.value):
                            bad_typed_keys.append(
                                f"{path.name}:{node.lineno}: {key} literal arg has CJK prose: {elt.value!r}"
                            )
            elif args_node is None and needed != 0:
                bad_typed_keys.append(
                    f"{path.name}:{node.lineno}: {key} expects {needed} args, got none"
                )

assert not raw_cjk_raises, raw_cjk_raises
assert not bad_typed_keys, bad_typed_keys

# Hades I Save Editor no longer wraps raw English prose in "hades.saveEditor.error".
hades1_en = json.loads((ROOT / "Sources/Hades/Presentation/Localization/hades.en.json").read_text(encoding="utf-8"))["entries"]
assert "hades.saveEditor.error" not in hades1_en
for path in [
    *sorted((ROOT / "Backend/games/hades").glob("*.py")),
    *sorted((ROOT / "Sources/Hades").rglob("*.swift")),
]:
    text = path.read_text(encoding="utf-8")
    assert '"hades.saveEditor.error"' not in text and "'hades.saveEditor.error'" not in text, path

print("hades2_error_registry_single_source_ok")
