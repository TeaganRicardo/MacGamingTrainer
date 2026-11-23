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

# Backend messages: interpolated values become arguments, never part of the
# key, and unregistered developer text is not reclassified as player copy.
assert error_presentation.presentation_for("请先启动 Hades II 并进入存档。") == ("hades2.error.gameNotRunning", ["Hades II"])
assert error_presentation.presentation_for("查询 Hades II 进程失败（-9）：boom") == (
    "hades2.error.processQueryFailed", ["Hades II", "-9", "boom"])
assert error_presentation.presentation_for("未知功能。") == ("hades2.error.unknownFeature", [])
assert error_presentation.presentation_for("Hades II module manifest is missing a valid steamAppId.")[0] is None

# The registry itself has no duplicate, invalid or shadowed rule; a shadowed
# rule silently sends a player's error to the wrong key.
assert not error_presentation.check_registry(), error_presentation.check_registry()
assert not error_presentation._unreachable(error_presentation.REGISTRY)

# Every player-facing message the Hades II backend raises maps to a key, fills
# every {n} of its English template, and passes no untranslated sentence text
# as an argument. Messages are read with `ast`, so f-strings, concatenation,
# `.format` and an assembled `message = ...` are seen as the player sees them.
EN = json.loads((ROOT / "Sources/Hades2/Presentation/Localization/hades2.en.json").read_text(encoding="utf-8"))["entries"]
CJK = re.compile(r"[㐀-鿿]")
STRING_ARG = re.compile(r"""f?['"]([^'"\n]+)['"]""")
TABLE_ENTRY = re.compile(r"""['"](?:error|message)['"]\s*:\s*f?['"]([^'"\n]+)['"]""")
BOUNDARY_DAMAGE = re.compile(r"[　-〿＀-￯]")
ERROR_SHAPED = re.compile(
    r"(失败|错误|无法|不可用|未连接|未运行|未解析|未经验证|需要|请先|请在|已保留|保持不变|不支持|"
    r"已结束|已退出|已断开|超时|不得|不能|拒绝|不再支持|不一致|不存在|未找到|未知)")
# Modules whose Chinese strings are labels or report data, never raised errors,
# and functions that return explicit bilingual row data (exempt only while they
# contain no raise).
ERROR_FREE_MODULES = {"catalog.py", "diagnostics.py", "save_history.py", "save_investigation.py"}
BILINGUAL_DATA_FUNCTIONS = {
    "save_advanced.py": {"row", "warning"},
    "save_workspace.py": {"_discovery_reason"},
    "save_narrative.py": {"entry_row"},
    "save_quest_rewards.py": {"rows"},
}


def shape(node):
    """The sentence a string expression renders, with runtime values as X."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(shape(value) for value in node.values)
    if isinstance(node, ast.FormattedValue):
        if isinstance(node.value, ast.Attribute):
            return shape(node.value)
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            return node.value.value
        return "X"
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = shape(node.left), shape(node.right)
        return (left + right) if left and right else (left or right or "X")
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
        return shape(node.left) + "X"
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "format":
            return re.sub(r"\{\}", "X", shape(func.value))
        if isinstance(func, ast.Attribute) and func.attr in {"join", "strip"}:
            return shape(func.value)
        if isinstance(func, ast.Name) and func.id in {"str", "repr", "format"}:
            return "X"
        return ""
    if isinstance(node, ast.Name):
        return "X" if node.id in {"message", "detail", "warning", "error"} else node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def raised_messages(tree):
    found = []
    for node in ast.walk(tree):
        arguments = []
        if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
            arguments = node.exc.args
            # `(code, message)` for Hades errors, `(message)` otherwise.
            if len(arguments) > 1 and isinstance(arguments[0], ast.Constant):
                arguments = arguments[1:]
        elif isinstance(node, ast.Assign) and isinstance(node.value, (ast.Constant, ast.JoinedStr)) and any(
                isinstance(target, ast.Name) and target.id == "message" for target in node.targets):
            arguments = [node.value]
        for argument in arguments:
            text = re.sub(r"\s+([。，、；：）】」』])", r"\1", re.sub(r"\s+", " ", shape(argument)).strip())
            if CJK.search(text):
                found.append(text)
    return found


unregistered = []
for path in sorted((ROOT / "Backend/games/hades2").glob("*.py")):
    if path.name == "error_presentation.py":
        continue
    body = path.read_text(encoding="utf-8")
    tree = ast.parse(body)
    messages = raised_messages(tree) + [match.group(1) for match in TABLE_ENTRY.finditer(body)]
    if path.name not in ERROR_FREE_MODULES:
        data_spans = [
            (node.lineno, node.end_lineno) for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name in BILINGUAL_DATA_FUNCTIONS.get(path.name, ())
            and not any(isinstance(child, ast.Raise) for child in ast.walk(node))
        ]
        messages += [
            literal.group(1) for literal in STRING_ARG.finditer(body)
            if CJK.search(literal.group(1)) and ERROR_SHAPED.search(literal.group(1))
            and not any(start <= body.count("\n", 0, literal.start()) + 1 <= end for start, end in data_spans)
        ]
    for message in messages:
        if not CJK.search(message):
            continue
        key, arguments = error_presentation.presentation_for(re.sub(r"\{[^}]*\}", "X", message))
        if key is None:
            unregistered.append(f"{path.name}: {message!r}")
            continue
        template = EN.get(key)
        assert template is not None, f"{key} is missing from the en table"
        assert len(arguments) == len(re.findall(r"\{(\d+)\}", template)), (path.name, message, key, arguments)
        for argument in arguments:
            assert not (argument and (CJK.search(argument) or BOUNDARY_DAMAGE.search(argument))), (
                f"{path.name}: {message!r} -> {key} argument {argument!r} carries untranslated sentence text")
assert not unregistered, sorted(set(unregistered))

print("hades2_error_registry_single_source_ok")
