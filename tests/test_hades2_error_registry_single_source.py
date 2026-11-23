"""Hades II runtime and backend errors map to presentation keys and arguments (#204)."""
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

print("hades2_error_registry_single_source_ok")
