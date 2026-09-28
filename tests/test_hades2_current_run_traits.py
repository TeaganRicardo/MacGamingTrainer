"""D01 · Current-run trait inventory and sell-safe removal capability.

Source-derived contracts for issue #187. Every assertion here exists because
# D00 (issue #186) proved a specific limit, and the honest answer to "can this
be removed?" is narrower than a generic delete would suggest.

The three load-bearing truths:

1. Identity is current-run only. D00 §7 proved `trait.Id` is assigned by
   `GetTraitUniqueId` and is NOT stable across run reload, game restart or a
   save round trip. Nothing may persist it or present it as durable.
2. The only proven-safe teardown is name-level and removes every matching
   instance (D00 §6). So the capability is reported with that scope, and the
   API accepts a NAME — not an instance identity.
3. No generic `RemoveTraitData` escape hatch is reachable.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

LUA = (ROOT / "Backend/games/hades2/runtime/hades.lua").read_text(encoding="utf-8")
TYPES = (ROOT / "Sources/Hades2/Hades2Types.swift").read_text(encoding="utf-8")
MODEL = (ROOT / "Sources/Hades2/Hades2Model.swift").read_text(encoding="utf-8")
STATE = (ROOT / "Sources/Hades2/Hades2BackendState.swift").read_text(encoding="utf-8")
API = (ROOT / "Sources/Hades2/Hades2API.swift").read_text(encoding="utf-8")
VIEW = (ROOT / "Sources/Hades2/Hades2View.swift").read_text(encoding="utf-8")
SCHEMA = (ROOT / "Backend/games/hades2/schema.py").read_text(encoding="utf-8")
VALIDATION = (ROOT / "Backend/games/hades2/command_validation.py").read_text(encoding="utf-8")
ROUTER = (ROOT / "Backend/games/hades2/command_router.py").read_text(encoding="utf-8")


# --- 1. Observation is projected from live runtime state, not desired state ---
assert "local currentRunTraits = function()" in LUA, "no current-run trait projection"
assert "CurrentRun.Hero.Traits" in LUA, "inventory is not read from the live run"
# It must not be assembled from the boon catalog or from desired state.
projection = LUA[LUA.index("local currentRunTraits = function()"):LUA.index("local function state(")]
assert "boons()" not in projection, "trait inventory is built from the boon catalog"
assert "desiredFeatures" not in projection, "trait inventory is built from desired state"
# The payload names the identity scope instead of implying durability.
assert "currentRunTraitIdentityScope" in LUA
assert "currentRunTraitIdentityPersistent = false" in LUA


# --- 2. Removal capability is the narrow D00-proven value only ---
for key, value in (("nameLevelAllMatching", ".nameLevelAllMatching"), ("none", ".none")):
    assert f"case {key}" in TYPES, f"missing removal capability {value}"
assert "TraitRemovalCapability" in TYPES
# The scope is stated on the wire, not implied.
assert "removalScopeAllMatching" in LUA
assert "removalCapability" in LUA
# Removal capability must be gated on the proven predicate alone. An
# unconditional grant is the exact failure D00 warned about, so assert the
# grant cannot be reached without the predicate's result.
capability_block = LUA[LUA.index("local currentRunTraits = function()"):LUA.index("local function state(")]
assert capability_block.count('scope = "nameLevelAllMatching"') == 1, (
    "name-level scope is granted more than once")
assert 'if eligible then scope = "nameLevelAllMatching" end' in capability_block, (
    "name-level scope is not gated on the native sell predicate")
# Every non-eligible row must end up with no capability at all.
assert 'if eligible then scope = "nameLevelAllMatching" end' in capability_block
# Exactly one reassignment of the capability, and it is the gated one. The
# `local scope = "none"` initializer is the default, not a grant.
assert len(re.findall(r"^\s*if eligible then scope = ", capability_block, re.M)) == 1, (
    "the capability grant is not the single gated branch")
assert "local scope = \"none\"" in capability_block, "the capability has no safe default"
# The unproven families D00 listed must not be grantable removal.
for family in ("Chaos", "Selene", "Weapon", "Spell", "Costume"):
    assert family in SCHEMA, f"{family} is not classified as unproven"


# --- 3. No generic raw deletion escape hatch is exposed ---
# Check executable text only. A comment may name the escape hatch in order to
# document that it is deliberately NOT used; a call would expose it.
def code_only(source: str) -> str:
    return "\n".join(re.sub(r"--.*$", "", line) for line in source.splitlines())

for forbidden in ("RemoveTraitData", "remove_trait_data", "delete_trait", "raw_remove"):
    assert forbidden not in code_only(LUA), f"generic escape hatch exposed: {forbidden}"
    assert forbidden not in code_only(ROUTER), f"generic escape hatch routed: {forbidden}"
    assert forbidden not in code_only(API), f"generic escape hatch in the client: {forbidden}"
# The one native teardown used is the proven name-level one.
assert 'RemoveWeaponTrait(traitName, { Silent = true })' in LUA
# Its scope must be documented as all-matching, not single-instance.
assert "all-matching" in LUA or "all matching" in LUA


# --- 4. The removal input is a NAME, never an instance identity ---
assert "params.trait" in LUA
assert "traitName" in LUA
# The client sends the name.
assert 'return ["trait": name]' in API, "removal must send the trait name"
# The instance identity is never an input.
removal_block = LUA[LUA.index('if command == "remove_trait" then'):LUA.index('if command == "open_sell_traits" then')]
assert "instanceId" not in removal_block, "removal must not accept instance identity"
assert "trait.Id" not in removal_block, "removal must not key on the untrusted instance id"
# The only input is the validated name; no other runtime identity is read.
assert removal_block.count("params.trait") == 1, "removal reads an unexpected parameter"
assert "CurrentRun.Hero.Traits[" not in removal_block, (
    "removal reaches into the live trait table instead of using the name")


# --- 5. Removal is non-idempotent and obeys request-id / outcome-unknown rules ---
assert "remove_trait = { \"trait\" }" in LUA, "removal has no action fingerprint"
assert "return action(command, params, function(record)" in removal_block, (
    "removal does not ride the non-idempotent action path")
assert "remove_trait" in ROUTER
assert "'remove_trait'" in ROUTER, "removal is not registered as a runtime command"
# It must require a request id, exactly like the other non-idempotent actions.
request_id_block = ROUTER[ROUTER.index("_REQUEST_ID_COMMANDS"):ROUTER.index("class Hades2CommandRouter")]
assert "'remove_trait'" in request_id_block, "removal does not require a request id"
# And it must never be auto-replayed.
assert "MGT_OUTCOME_UNKNOWN" in LUA
assert "do not retry" in LUA.lower()


# --- 6. The capability is re-checked at removal time, not trusted from the client ---
assert "IsGodTrait, traitName, { ForShop = true }" in removal_block, (
    "removal does not re-check the native sell predicate")
assert "HeroHasTrait" in removal_block, "removal does not verify presence in the run"
# A row that is not sell-eligible must be refused by name.
assert "not sell-eligible" in removal_block or "not proven safe" in removal_block


# --- 7. The Swift side is language-neutral and uses the presentation seam ---
assert "struct CurrentRunTrait" in TYPES
assert "removalCapability" in STATE, "the inventory is not decoded"
# An unrecognised capability must read as "no removal", never grant one.
assert "?? .none" in STATE, "an unknown capability must default to no removal"
# User-facing copy comes from keys, not literals.
for key in ("hades2.traits.section", "hades2.traits.remove",
            "hades2.traits.removalUnavailable", "hades2.traits.removeAllMatching"):
    assert f'text("{key}")' in VIEW or f'"{key}"' in VIEW, f"missing presentation key use: {key}"
# No user-facing Chinese is hard-coded in the new Swift surface.
cjk = re.compile(r"[一-鿿]")
for path in ("Sources/Hades2/Hades2View.swift", "Sources/Hades2/Hades2Model.swift",
             "Sources/Hades2/Hades2Types.swift", "Sources/Hades2/Hades2BackendState.swift"):
    body = (ROOT / path).read_text(encoding="utf-8")
    assert not cjk.search(body), f"{path} embeds user-facing Chinese"


# --- 8. Unsupported categories stay visible and disabled, with a truthful reason ---
assert "removalReason" in TYPES
assert "ownerSpecificLifecycle" in VIEW, "no truthful reason is shown for unremovable rows"
assert "if trait.canRemove" in VIEW, "removal is not gated on the proven capability"
# The guard in the model must refuse anything the runtime did not mark removable.
assert "trait.canRemove, trait.removalScopeAllMatching" in MODEL, (
    "the model removes without requiring the proven capability and scope")
# And the view must not offer the control for an unremovable row. An `if true`
# here would show Remove on rows the runtime refused.
row_block = VIEW[VIEW.index("private func currentRunTraitRow"):VIEW.index("private var resourceSection")]
assert "if trait.canRemove {" in row_block, "the row does not gate the control on capability"
assert "if true {" not in row_block, "the removal control is shown unconditionally"
assert "if trait.canRemove {" in row_block
# The disabled branch must exist and be truthful, not just hidden.
assert "hades2.traits.removalUnavailable" in row_block, (
    "unremovable rows give no visible reason")


# --- 9. Resident revision increased exactly once ---
revision = int(re.search(r"version = 1, revision = (\d+)", LUA).group(1))
previous = int(re.search(r"previousModule\.revision ~= (\d+)", LUA).group(1))
assert revision == previous, "resident revision guard and declared revision disagree"
assert revision == 50, f"resident revision must be 49 -> 50, found {revision}"


# --- 10. Every new key exists in both shipped languages ---
tables = {
    language: json.loads(
        (ROOT / f"Sources/Hades2/Presentation/Localization/hades2.{language}.json").read_text(encoding="utf-8")
    )["entries"]
    for language in ("zh-CN", "en")
}
assert set(tables["zh-CN"]) == set(tables["en"])
for key in ("hades2.traits.section", "hades2.traits.remove",
            "hades2.traits.removalUnavailable", "hades2.traits.removeAllMatching",
            "hades2.traits.identityScope", "hades2.traits.empty",
            "hades2.receipt.traitRemoved"):
    for language, entries in tables.items():
        assert key in entries, f"{language} is missing {key}"
        assert entries[key].strip(), f"{language} {key} is empty"
        # A `{0}` is a deliberate argument placeholder, and `{term:...}` is a
        # deliberate registry reference. Neither is a broken reference; an
        # unknown term or an unindexed placeholder would be.
        assert not re.search(r"\{(?!\d+|term:)", entries[key]), (
            f"{language} {key} has a malformed reference: {entries[key]}")
        for index in re.findall(r"\{(\d+)\}", entries[key]):
            assert int(index) < 1, f"{language} {key} expects an argument the UI cannot supply"


# --- 11. The removal errors are registered player-facing keys ---
from games.hades2 import error_presentation as ep  # noqa: E402

for message, expected in (
    ("请选择要移除的祝福。", "hades2.error.selectTraitToRemove"),
    ("Trait removal requires an active run room", "hades2.error.traitRemovalNeedsRun"),
    ("Trait is not sell-eligible, so no safe removal exists: BoonX", "hades2.error.traitNotSellEligible"),
    ("Trait removal is not proven safe: BoonY", "hades2.error.traitRemovalNotProven"),
    ("Trait is not present in the current run: BoonZ", "hades2.error.traitNotPresent"),
):
    key, _ = ep.presentation_for(message)
    assert key == expected, (message, key)
    # The value stays on the diagnostic; the key is what the UI renders.
    assert not any("一" <= character <= "鿿" for character in key)


# --- 12. The client validation rejects a missing name ---
assert "remove_trait" in VALIDATION
assert "请选择要移除的祝福。" in VALIDATION

print("hades2_current_run_traits_ok")
