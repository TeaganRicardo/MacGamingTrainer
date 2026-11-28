"""Hades II player-facing error identity.

A user-facing failure must be readable in every supported language, but the
backend does not know the Host language. So a Hades-owned failure carries a
stable presentation *key* on the wire; the shipped bilingual tables
(`Sources/Hades2/Presentation/Localization/hades2.<lang>.json`) own the wording and
the Host resolves the key when it renders the message.

Python raise sites construct `Hades2PresentationError`, `Hades2ValueError`,
`Hades2RuntimeError`, or `SaveBatchValidationError` directly with their `key`,
`arguments`, and `diagnostic`. `REGISTRY` owns resident-Lua runtime text
resolution only, where errors arrive from inside the game as strings.
"""
from dataclasses import dataclass, field
import re
from typing import Sequence

from core.adapter import AdapterError
from core.errors import PresentableError


@dataclass(frozen=True)
class Hades2PresentationKey:
    """A language-neutral player-facing message identity.

    `key` resolves in every shipped language. `arguments` fill its `{n}`
    placeholders and are runtime values, not copy: a game display name, a
    process name, or a raw tool error.
    """

    key: str
    arguments: Sequence[str] = field(default_factory=tuple)

    def render(self, template: str) -> str:
        """Fill this key's template with its arguments."""
        result = template
        for index, argument in enumerate(self.arguments):
            result = result.replace('{%d}' % index, argument)
        return result


class Hades2PresentationError(AdapterError):
    """A Hades failure whose player-facing value is a presentation key.

    `presentation` is the key and `diagnostic` keeps the readable text.
    `arguments` fills the key's `{n}` placeholders and travels alongside the
    key in the Core-owned `error.arguments` envelope field, so the Host can
    render the module's own sentence in the player's language.
    """

    def __init__(self, code, key, arguments=(), *, diagnostic=None):
        # Routed through the Core constructor so every AdapterError exposes one
        # shape for `arguments`; assigning it here produced a second one.
        super().__init__(code, key, diagnostic=diagnostic, arguments=arguments)


class Hades2ValueError(PresentableError, ValueError):
    """Validation failure carrying a Hades-owned presentation key."""

    def __init__(self, key: str, diagnostic: str, arguments=(), *, code: str = 'invalid_request'):
        super().__init__(code, key, diagnostic=diagnostic, arguments=arguments, message=diagnostic)


class Hades2RuntimeError(PresentableError, RuntimeError):
    """System/preparation failure carrying a Hades-owned presentation key."""

    def __init__(self, key: str, diagnostic: str, arguments=(), *, code: str = 'invalid_request'):
        super().__init__(code, key, diagnostic=diagnostic, arguments=arguments, message=diagnostic)


class SaveBatchValidationError(Hades2ValueError):
    """Staged Save Editor batch rejection with category and optional action IDs."""

    def __init__(self, key: str, diagnostic: str, category: str, action_ids=()):
        super().__init__(key, diagnostic)
        self.batch_category = category
        self.action_ids = tuple(sorted(set(action_ids)))


# ---------------------------------------------------------------------------
# Resident-Lua runtime error registry
# ---------------------------------------------------------------------------
#
# `REGISTRY` maps messages raised inside the resident Lua runtime to Hades
# presentation keys. Every rule carries `runtime` provenance naming the
# resident command(s) and helper/command producer. ORDER IS SEMANTIC: rules are
# tried top to bottom and the first match wins.

REGISTRY = [
    {'match': 'literal', 'message': 'Resident update is waiting for an accepted action to finish', 'key': 'hades2.error.residentActionPending', 'runtime': {'commands': '*', 'producer': {'kind': 'helper', 'name': 'resident bootstrap'}}},
    {'match': 'literal', 'message': 'hades2.garden.unavailable', 'key': 'hades2.garden.unavailable', 'runtime': {'commands': ['mature_garden'], 'producer': {'kind': 'helper', 'name': 'prepareGardenMaturity'}}},
    {'match': 'literal', 'message': 'Disable Infinite Gold before selecting a fixed-value gold lock', 'key': 'hades2.error.infiniteMoneyLockConflict', 'runtime': {'commands': ['lock_resource'], 'producer': {'kind': 'command', 'name': 'lock_resource'}}},
    {'match': 'literal', 'message': 'Disable Infinite Rerolls before selecting a fixed-value reroll lock', 'key': 'hades2.error.infiniteRerollsLockConflict', 'runtime': {'commands': ['lock_rerolls'], 'producer': {'kind': 'command', 'name': 'lock_rerolls'}}},
    {'match': 'literal', 'message': 'Invalid Chaos Gate probability', 'key': 'hades2.error.percentRange', 'runtime': {'commands': ['set_chaos_gate_probability'], 'producer': {'kind': 'helper', 'name': 'setChaosProbability'}}},
    {'match': 'literal', 'message': 'hades2.chaosGate.unavailable.scene', 'key': 'hades2.chaosGate.unavailable.scene', 'runtime': {'commands': ['generate_chaos_gate'], 'producer': {'kind': 'helper', 'name': 'inspectChaos'}}},
    {'match': 'literal', 'message': 'hades2.chaosGate.unavailable.native', 'key': 'hades2.chaosGate.unavailable.native', 'runtime': {'commands': ['generate_chaos_gate'], 'producer': {'kind': 'helper', 'name': 'inspectChaos'}}},
    {'match': 'literal', 'message': 'hades2.chaosGate.unavailable.existing', 'key': 'hades2.chaosGate.unavailable.existing', 'runtime': {'commands': ['generate_chaos_gate'], 'producer': {'kind': 'helper', 'name': 'inspectChaos'}}},
    {'match': 'literal', 'message': 'hades2.chaosGate.unavailable.progression', 'key': 'hades2.chaosGate.unavailable.progression', 'runtime': {'commands': ['generate_chaos_gate'], 'producer': {'kind': 'helper', 'name': 'inspectChaos'}}},
    {'match': 'literal', 'message': 'hades2.chaosGate.unavailable.route', 'key': 'hades2.chaosGate.unavailable.route', 'runtime': {'commands': ['generate_chaos_gate'], 'producer': {'kind': 'helper', 'name': 'inspectChaos'}}},
    {'match': 'literal', 'message': 'hades2.chaosGate.unavailable.placement', 'key': 'hades2.chaosGate.unavailable.placement', 'runtime': {'commands': ['generate_chaos_gate'], 'producer': {'kind': 'helper', 'name': 'inspectChaos'}}},
    {'match': 'literal', 'message': 'hades2.chaosGate.unavailable.stale', 'key': 'hades2.chaosGate.unavailable.stale', 'runtime': {'commands': ['generate_chaos_gate'], 'producer': {'kind': 'helper', 'name': 'prepareCurrentChaosGate'}}},
    {'match': 'literal', 'message': 'hades2.facility.unavailable.scene', 'key': 'hades2.facility.unavailable.scene', 'runtime': {'commands': ['generate_chamber_facility'], 'producer': {'kind': 'helper', 'name': 'inspectFacility'}}},
    {'match': 'literal', 'message': 'hades2.facility.unavailable.native', 'key': 'hades2.facility.unavailable.native', 'runtime': {'commands': ['generate_chamber_facility'], 'producer': {'kind': 'helper', 'name': 'inspectFacility'}}},
    {'match': 'literal', 'message': 'hades2.facility.unavailable.route', 'key': 'hades2.facility.unavailable.route', 'runtime': {'commands': ['generate_chamber_facility'], 'producer': {'kind': 'helper', 'name': 'inspectFacility'}}},
    {'match': 'literal', 'message': 'hades2.facility.unavailable.progression', 'key': 'hades2.facility.unavailable.progression', 'runtime': {'commands': ['generate_chamber_facility'], 'producer': {'kind': 'helper', 'name': 'inspectFacility'}}},
    {'match': 'literal', 'message': 'hades2.facility.unavailable.existing', 'key': 'hades2.facility.unavailable.existing', 'runtime': {'commands': ['generate_chamber_facility'], 'producer': {'kind': 'helper', 'name': 'inspectFacility'}}},
    {'match': 'literal', 'message': 'hades2.facility.unavailable.placement', 'key': 'hades2.facility.unavailable.placement', 'runtime': {'commands': ['generate_chamber_facility'], 'producer': {'kind': 'helper', 'name': 'inspectFacility'}}},
    {'match': 'literal', 'message': 'hades2.facility.unavailable.stock', 'key': 'hades2.facility.unavailable.stock', 'runtime': {'commands': ['generate_chamber_facility'], 'producer': {'kind': 'helper', 'name': 'inspectFacility'}}},
    {'match': 'literal', 'message': 'hades2.facility.unavailable.fear', 'key': 'hades2.facility.unavailable.fear', 'runtime': {'commands': ['generate_chamber_facility'], 'producer': {'kind': 'helper', 'name': 'inspectFacility'}}},
    {'match': 'literal', 'message': 'hades2.facility.unavailable.encounter', 'key': 'hades2.facility.unavailable.encounter', 'runtime': {'commands': ['generate_chamber_facility'], 'producer': {'kind': 'helper', 'name': 'inspectFacility'}}},
    {'match': 'literal', 'message': 'hades2.facility.unavailable.stale', 'key': 'hades2.facility.unavailable.stale', 'runtime': {'commands': ['generate_chamber_facility'], 'producer': {'kind': 'helper', 'name': 'prepareFacility'}}},
    {'match': 'literal', 'message': 'hades2.gathering.unavailable.polymorph', 'key': 'hades2.gathering.unavailable.polymorph', 'runtime': {'commands': ['generate_gathering'], 'producer': {'kind': 'helper', 'name': 'inspect'}}},
    {'match': 'literal', 'message': 'hades2.gathering.unavailable.scene', 'key': 'hades2.gathering.unavailable.scene', 'runtime': {'commands': ['generate_gathering'], 'producer': {'kind': 'helper', 'name': 'inspect'}}},
    {'match': 'literal', 'message': 'hades2.gathering.unavailable.native', 'key': 'hades2.gathering.unavailable.native', 'runtime': {'commands': ['generate_gathering'], 'producer': {'kind': 'helper', 'name': 'inspect'}}},
    {'match': 'literal', 'message': 'hades2.gathering.unavailable.familiar', 'key': 'hades2.gathering.unavailable.familiar', 'runtime': {'commands': ['generate_gathering'], 'producer': {'kind': 'helper', 'name': 'inspect'}}},
    {'match': 'literal', 'message': 'hades2.gathering.unavailable.tool', 'key': 'hades2.gathering.unavailable.tool', 'runtime': {'commands': ['generate_gathering'], 'producer': {'kind': 'helper', 'name': 'inspect'}}},
    {'match': 'literal', 'message': 'hades2.gathering.unavailable.complex', 'key': 'hades2.gathering.unavailable.complex', 'runtime': {'commands': ['generate_gathering'], 'producer': {'kind': 'helper', 'name': 'inspect'}}},
    {'match': 'literal', 'message': 'hades2.gathering.unavailable.lava', 'key': 'hades2.gathering.unavailable.lava', 'runtime': {'commands': ['generate_gathering'], 'producer': {'kind': 'helper', 'name': 'inspect'}}},
    {'match': 'literal', 'message': 'hades2.gathering.unavailable.existing', 'key': 'hades2.gathering.unavailable.existing', 'runtime': {'commands': ['generate_gathering'], 'producer': {'kind': 'helper', 'name': 'inspect'}}},
    {'match': 'literal', 'message': 'hades2.gathering.unavailable.placement', 'key': 'hades2.gathering.unavailable.placement', 'runtime': {'commands': ['generate_gathering'], 'producer': {'kind': 'helper', 'name': 'inspect'}}},
    {'match': 'literal', 'message': 'hades2.gathering.unavailable.pool', 'key': 'hades2.gathering.unavailable.pool', 'runtime': {'commands': ['generate_gathering'], 'producer': {'kind': 'helper', 'name': 'inspect'}}},
    {'match': 'literal', 'message': 'hades2.gathering.unavailable.stale', 'key': 'hades2.gathering.unavailable.stale', 'runtime': {'commands': ['generate_gathering'], 'producer': {'kind': 'helper', 'name': 'prepare'}}},
    {'match': 'literal', 'message': 'Selected boon is already owned', 'key': 'hades2.error.exactAlreadyOwned', 'runtime': {'commands': ['spawn_reward', 'acquire_chaos_pair'], 'producer': {'kind': 'helper', 'name': 'prepareExactReward'}}},
    {'match': 'literal', 'message': 'Selected boon is not currently eligible', 'key': 'hades2.error.exactNotEligible', 'runtime': {'commands': ['spawn_reward'], 'producer': {'kind': 'helper', 'name': 'prepareExactReward'}}},
    {'match': 'literal', 'message': 'Selected boon does not support the requested rarity', 'key': 'hades2.error.exactRarityUnsupported', 'runtime': {'commands': ['spawn_reward', 'acquire_chaos_pair'], 'producer': {'kind': 'helper', 'name': 'requestedAcquisition'}}},
    {'match': 'literal', 'message': 'Selected boon does not support the requested level', 'key': 'hades2.error.exactLevelUnsupported', 'runtime': {'commands': ['spawn_reward', 'acquire_chaos_pair'], 'producer': {'kind': 'helper', 'name': 'requestedAcquisition'}}},
    {'match': 'literal', 'message': 'Echo previous-run boon is no longer eligible', 'key': 'hades2.error.exactNotEligible', 'runtime': {'commands': ['spawn_reward'], 'producer': {'kind': 'helper', 'name': 'prepareExactReward'}}},
    {'match': 'literal', 'message': 'Echo previous-run boon acquisition failed', 'key': 'hades2.error.echoLastRunFailed', 'runtime': {'commands': ['spawn_reward'], 'producer': {'kind': 'helper', 'name': 'applyPreviousRunExact'}}},
    {'match': 'literal', 'message': 'Trait mutation requires a live trait owner', 'key': 'hades2.error.traitMutationNeedsOwner', 'runtime': {'commands': ['set_trait_level', 'set_trait_rarity', 'set_trait_remaining_uses', 'expire_trait', 'remove_trait', 'advance_trait_lifecycle'], 'producer': {'kind': 'helper', 'name': 'resolveTraitTarget'}}},
    {'match': 'literal', 'message': 'Trait selection belongs to a stale runtime generation', 'key': 'hades2.error.traitSelectionStale', 'runtime': {'commands': ['set_trait_level', 'set_trait_rarity', 'set_trait_remaining_uses', 'expire_trait', 'remove_trait', 'advance_trait_lifecycle'], 'producer': {'kind': 'helper', 'name': 'resolveTraitTarget'}}},
    {'match': 'literal', 'message': 'Trait selection belongs to a stale run', 'key': 'hades2.error.traitSelectionStale', 'runtime': {'commands': ['set_trait_level', 'set_trait_rarity', 'set_trait_remaining_uses', 'expire_trait', 'remove_trait', 'advance_trait_lifecycle'], 'producer': {'kind': 'helper', 'name': 'resolveTraitTarget'}}},
    {'match': 'literal', 'message': 'Trait instance is no longer present', 'key': 'hades2.error.traitTargetMissing', 'runtime': {'commands': ['set_trait_level', 'set_trait_rarity', 'set_trait_remaining_uses', 'expire_trait', 'remove_trait', 'advance_trait_lifecycle'], 'producer': {'kind': 'helper', 'name': 'resolveTraitTarget'}}},
    {'match': 'literal', 'message': 'Trait target changed since selection', 'key': 'hades2.error.traitTargetChanged', 'runtime': {'commands': ['set_trait_level', 'set_trait_rarity', 'set_trait_remaining_uses', 'expire_trait', 'remove_trait', 'advance_trait_lifecycle'], 'producer': {'kind': 'helper', 'name': 'resolveTraitTarget'}}},
    {'match': 'literal', 'message': 'Trait level editing is unavailable for the selected target', 'key': 'hades2.error.traitLevelUnavailable', 'runtime': {'commands': ['set_trait_level'], 'producer': {'kind': 'command', 'name': 'set_trait_level'}}},
    {'match': 'literal', 'message': 'Trait target level must be higher than the current level', 'key': 'hades2.error.traitLevelTargetInvalid', 'runtime': {'commands': ['set_trait_level'], 'producer': {'kind': 'command', 'name': 'set_trait_level'}}},
    {'match': 'literal', 'message': 'Trait is no longer eligible for a meaningful level increase', 'key': 'hades2.error.traitLevelNoLongerEligible', 'runtime': {'commands': ['set_trait_level'], 'producer': {'kind': 'command', 'name': 'set_trait_level'}}},
    {'match': 'literal', 'message': 'Trait level increase did not reach the requested target level', 'key': 'hades2.error.traitLevelNoEffect', 'runtime': {'commands': ['set_trait_level'], 'producer': {'kind': 'command', 'name': 'set_trait_level'}}},
    {'match': 'literal', 'message': 'Trait rarity editing is unavailable for the selected target', 'key': 'hades2.error.traitRarityUnavailable', 'runtime': {'commands': ['set_trait_rarity'], 'producer': {'kind': 'command', 'name': 'set_trait_rarity'}}},
    {'match': 'literal', 'message': 'Trait rarity recompute did not reach the requested rarity', 'key': 'hades2.error.traitRarityNoEffect', 'runtime': {'commands': ['set_trait_rarity'], 'producer': {'kind': 'command', 'name': 'set_trait_rarity'}}},
    {'match': 'literal', 'message': 'Trait removal is unavailable for the selected target', 'key': 'hades2.error.traitRemovalUnavailable', 'runtime': {'commands': ['remove_trait'], 'producer': {'kind': 'command', 'name': 'remove_trait'}}},
    {'match': 'literal', 'message': 'Trait removal capability is unknown', 'key': 'hades2.error.traitRemovalCapabilityUnknown', 'runtime': {'commands': ['remove_trait'], 'producer': {'kind': 'command', 'name': 'remove_trait'}}},
    {'match': 'literal', 'message': 'Direct trait removal left the selected instance mounted', 'key': 'hades2.error.traitRemovalNoEffect', 'runtime': {'commands': ['remove_trait'], 'producer': {'kind': 'command', 'name': 'remove_trait'}}},
    {'match': 'literal', 'message': 'Temporary effect duration editing is unavailable for the selected target', 'key': 'hades2.error.traitDurationUnavailable', 'runtime': {'commands': ['set_trait_remaining_uses'], 'producer': {'kind': 'command', 'name': 'set_trait_remaining_uses'}}},
    {'match': 'literal', 'message': 'Temporary effect duration did not reach the requested remaining uses', 'key': 'hades2.error.traitDurationNoEffect', 'runtime': {'commands': ['set_trait_remaining_uses', 'expire_trait'], 'producer': {'kind': 'helper', 'name': 'setCounter'}}},
    {'match': 'literal', 'message': 'Temporary effect expiry is unavailable for the selected target', 'key': 'hades2.error.traitExpiryUnavailable', 'runtime': {'commands': ['expire_trait'], 'producer': {'kind': 'command', 'name': 'expire_trait'}}},
    {'match': 'literal', 'message': 'Temporary effect expiry left the selected instance mounted', 'key': 'hades2.error.traitRemovalNoEffect', 'runtime': {'commands': ['expire_trait'], 'producer': {'kind': 'helper', 'name': 'expire'}}},
    {'match': 'literal', 'message': 'Temporary effect cancellation left the selected instance mounted', 'key': 'hades2.error.traitRemovalNoEffect', 'runtime': {'commands': ['remove_trait'], 'producer': {'kind': 'helper', 'name': 'cancel'}}},
    {'match': 'literal', 'message': 'Familiar owner removal is unavailable', 'key': 'hades2.error.traitRemovalUnavailable', 'runtime': {'commands': ['remove_trait'], 'producer': {'kind': 'helper', 'name': 'teardownOwner'}}},
    {'match': 'literal', 'message': 'Familiar owner removal left a mounted trait', 'key': 'hades2.error.traitRemovalNoEffect', 'runtime': {'commands': ['remove_trait'], 'producer': {'kind': 'helper', 'name': 'teardownOwner'}}},
    {'match': 'literal', 'message': 'Familiar owner removal left the owner equipped', 'key': 'hades2.error.traitRemovalNoEffect', 'runtime': {'commands': ['remove_trait'], 'producer': {'kind': 'helper', 'name': 'teardownOwner'}}},
    {'match': 'literal', 'message': 'Keepsake owner removal is unavailable', 'key': 'hades2.error.traitRemovalUnavailable', 'runtime': {'commands': ['remove_trait'], 'producer': {'kind': 'helper', 'name': 'teardownOwner'}}},
    {'match': 'literal', 'message': 'Keepsake owner removal left the selected trait mounted', 'key': 'hades2.error.traitRemovalNoEffect', 'runtime': {'commands': ['remove_trait'], 'producer': {'kind': 'helper', 'name': 'teardownOwner'}}},
    {'match': 'literal', 'message': 'Chaos trait editing is unavailable', 'key': 'hades2.error.chaosTraitEditUnavailable', 'runtime': {'commands': ['set_trait_level', 'set_trait_rarity'], 'producer': {'kind': 'helper', 'name': 'rebuildChaosTarget'}}},
    {'match': 'literal', 'message': 'Chaos trait edit failed', 'key': 'hades2.error.chaosTraitEditFailed', 'runtime': {'commands': ['set_trait_level', 'set_trait_rarity'], 'producer': {'kind': 'helper', 'name': 'rebuildChaosTarget'}}},
    {'match': 'literal', 'message': 'Chaos lifecycle transition is unavailable', 'key': 'hades2.error.chaosLifecycleUnavailable', 'runtime': {'commands': ['advance_trait_lifecycle'], 'producer': {'kind': 'command', 'name': 'advance_trait_lifecycle'}}},
    {'match': 'literal', 'message': 'Chaos lifecycle transition failed', 'key': 'hades2.error.chaosLifecycleFailed', 'runtime': {'commands': ['advance_trait_lifecycle'], 'producer': {'kind': 'command', 'name': 'advance_trait_lifecycle'}}},
    {'match': 'literal', 'message': 'Chaos exact acquisition is unavailable', 'key': 'hades2.error.chaosExactUnavailable', 'runtime': {'commands': ['spawn_reward', 'acquire_chaos_pair'], 'producer': {'kind': 'helper', 'name': 'prepareChaos'}}},
    {'match': 'literal', 'message': 'Chaos exact acquisition failed', 'key': 'hades2.error.chaosExactFailed', 'runtime': {'commands': ['spawn_reward', 'acquire_chaos_pair'], 'producer': {'kind': 'helper', 'name': 'runChaos'}}},
    {'match': 'literal', 'message': 'Chaos encounter count must be a whole number from 1 to 100', 'key': 'hades2.error.chaosEncountersRange', 'runtime': {'commands': ['acquire_chaos_pair'], 'producer': {'kind': 'helper', 'name': 'prepare'}}},
    {'match': 'literal', 'message': 'Selene spell target is unavailable', 'key': 'hades2.error.exactNotEligible', 'runtime': {'commands': ['spawn_reward'], 'producer': {'kind': 'helper', 'name': 'prepareExactReward'}}},
    {'match': 'literal', 'message': 'Selene talent is unavailable for the current Path of Stars', 'key': 'hades2.error.exactNotEligible', 'runtime': {'commands': ['spawn_reward'], 'producer': {'kind': 'helper', 'name': 'prepareExactReward'}}},
    {'match': 'literal', 'message': 'Selene talent is no longer available in the current Path of Stars', 'key': 'hades2.error.exactNotEligible', 'runtime': {'commands': ['spawn_reward'], 'producer': {'kind': 'helper', 'name': 'applyTalent'}}},
    {'match': 'literal', 'message': 'Mounted Selene talent is unavailable', 'key': 'hades2.error.exactNotEligible', 'runtime': {'commands': ['spawn_reward'], 'producer': {'kind': 'helper', 'name': 'applyTalent'}}},
    {'match': 'literal', 'message': 'Selene spell acquisition failed', 'key': 'hades2.error.seleneExactFailed', 'runtime': {'commands': ['spawn_reward'], 'producer': {'kind': 'helper', 'name': 'applySpell'}}},
    {'match': 'literal', 'message': 'Selene talent acquisition failed', 'key': 'hades2.error.seleneExactFailed', 'runtime': {'commands': ['spawn_reward'], 'producer': {'kind': 'helper', 'name': 'applyTalent'}}},
    {'match': 'literal', 'message': 'Not enough uninvested Path of Stars nodes remain for the requested level', 'key': 'hades2.error.traitLevelNoLongerEligible', 'runtime': {'commands': ['set_trait_level'], 'producer': {'kind': 'command', 'name': 'set_trait_level'}}},
    {'match': 'literal', 'message': 'Selene talent tree changed before the requested level was applied', 'key': 'hades2.error.traitTargetChanged', 'runtime': {'commands': ['set_trait_level'], 'producer': {'kind': 'command', 'name': 'set_trait_level'}}},
    {'match': 'literal', 'message': 'Selene spell removal left owner state mounted', 'key': 'hades2.error.traitRemovalNoEffect', 'runtime': {'commands': ['remove_trait'], 'producer': {'kind': 'command', 'name': 'remove_trait'}}},
    {'match': 'literal', 'message': 'Selene talent removal left the mounted effect present', 'key': 'hades2.error.traitRemovalNoEffect', 'runtime': {'commands': ['remove_trait'], 'producer': {'kind': 'command', 'name': 'remove_trait'}}},
    {'match': 'literal', 'message': 'Exact costume target is unavailable', 'key': 'hades2.error.exactNotEligible', 'runtime': {'commands': ['spawn_reward'], 'producer': {'kind': 'helper', 'name': 'prepareExactReward'}}},
    {'match': 'literal', 'message': 'Arachne costume acquisition failed', 'key': 'hades2.error.costumeOwnerFailed', 'runtime': {'commands': ['spawn_reward'], 'producer': {'kind': 'helper', 'name': 'applyCostume'}}},
    {'match': 'literal', 'message': 'Arachne costume replacement left previous owner mounted', 'key': 'hades2.error.costumeOwnerFailed', 'runtime': {'commands': ['spawn_reward'], 'producer': {'kind': 'helper', 'name': 'applyCostume'}}},
    {'match': 'literal', 'message': 'Arachne costume removal left owner state mounted', 'key': 'hades2.error.traitRemovalNoEffect', 'runtime': {'commands': ['remove_trait'], 'producer': {'kind': 'helper', 'name': 'removeCostume'}}},
    {'match': 'literal', 'message': 'Cannot open boon sell screen while another screen is active', 'key': 'hades2.error.sellScreenBusy', 'runtime': {'commands': ['open_sell_traits'], 'producer': {'kind': 'command', 'name': 'open_sell_traits'}}},
    {'match': 'literal', 'message': 'Boon selling requires a live trait owner', 'key': 'hades2.error.sellNeedsTraitOwner', 'runtime': {'commands': ['open_sell_traits'], 'producer': {'kind': 'command', 'name': 'open_sell_traits'}}},
    {'match': 'literal', 'message': 'Native boon sell screen data is unavailable', 'key': 'hades2.error.sellDataUnavailable', 'runtime': {'commands': ['open_sell_traits'], 'producer': {'kind': 'command', 'name': 'open_sell_traits'}}},
    {'match': 'literal', 'message': 'Action requires a requestId of 1..128 characters', 'key': 'hades2.error.requestIdRequired', 'runtime': {'commands': ['set_trait_level', 'set_trait_rarity', 'set_trait_remaining_uses', 'expire_trait', 'remove_trait', 'advance_trait_lifecycle', 'acquire_chaos_pair'], 'producer': {'kind': 'helper', 'name': 'action'}}},
    {'match': 'literal', 'message': 'requestId reused for a different action', 'key': 'hades2.error.requestIdReused', 'runtime': {'commands': ['set_trait_level', 'set_trait_rarity', 'set_trait_remaining_uses', 'expire_trait', 'remove_trait', 'advance_trait_lifecycle', 'acquire_chaos_pair'], 'producer': {'kind': 'helper', 'name': 'action'}}},
    {'match': 'literal', 'message': 'MGT_OUTCOME_UNKNOWN: Previous action outcome is unknown; do not retry', 'key': 'hades2.error.outcomeUnknownRuntime', 'runtime': {'commands': ['set_trait_level', 'set_trait_rarity', 'set_trait_remaining_uses', 'expire_trait', 'remove_trait', 'advance_trait_lifecycle', 'acquire_chaos_pair'], 'producer': {'kind': 'helper', 'name': 'action'}}},
    {'match': 'literal', 'message': 'Cannot open special blessing choice while another screen is active', 'key': 'hades2.error.choiceScreenBusy', 'runtime': {'commands': ['open_special_choice'], 'producer': {'kind': 'command', 'name': 'open_special_choice'}}},
    {'match': 'literal', 'message': 'Cannot open special blessing choice during a transition', 'key': 'hades2.error.choiceDuringTransition', 'runtime': {'commands': ['open_special_choice'], 'producer': {'kind': 'command', 'name': 'open_special_choice'}}},
    {'match': 'literal', 'message': 'Special blessing choice requires a live Hero/run owner', 'key': 'hades2.error.choiceNeedsHeroOwner', 'runtime': {'commands': ['open_special_choice'], 'producer': {'kind': 'command', 'name': 'open_special_choice'}}},
    {'match': 'literal', 'message': 'Special blessing source has no audited native choice flow', 'key': 'hades2.error.choiceNoAuditedFlow', 'runtime': {'commands': ['open_special_choice'], 'producer': {'kind': 'command', 'name': 'open_special_choice'}}},
    {'match': 'literal', 'message': 'Special blessing source data is unavailable', 'key': 'hades2.error.choiceSourceUnavailable', 'runtime': {'commands': ['open_special_choice'], 'producer': {'kind': 'command', 'name': 'open_special_choice'}}},
    {'match': 'literal', 'message': 'Special blessing choice data is unavailable', 'key': 'hades2.error.choiceDataUnavailable', 'runtime': {'commands': ['open_special_choice'], 'producer': {'kind': 'command', 'name': 'open_special_choice'}}},
    {'match': 'literal', 'message': 'No eligible special blessings are available', 'key': 'hades2.error.noEligibleSpecialRewards', 'runtime': {'commands': ['open_special_choice'], 'producer': {'kind': 'helper', 'name': 'fixedPlan'}}},
    {'match': 'regex', 'pattern': '^Unsupported (?P<purpose>.+?): missing (?P<missing>.+)$', 'key': 'hades2.error.nativeFunctionMissing', 'argument': 'groups', 'runtime': {'commands': '*', 'producer': {'kind': 'helper', 'name': 'requireFunctions'}, 'sample': 'Unsupported sample-purpose: missing SampleFunction'}},
    {'match': 'literal', 'message': 'Unsupported next occurrence target', 'key': 'hades2.error.invalidNextOccurrence', 'runtime': {'commands': ['apply_world_occurrence'], 'producer': {'kind': 'command', 'name': 'apply_world_occurrence'}}},
]

RUNTIME_FALLBACK_KEY = 'hades2.error.runtimeActionFailed'


def check_registry(registry=None) -> list:
    """Return structural problems in the resident-Lua runtime registry, if any."""
    registry = REGISTRY if registry is None else registry
    problems = []
    seen_literals = {}
    for index, rule in enumerate(registry):
        shape = rule.get('match')
        if shape not in ('literal', 'prefix', 'regex'):
            problems.append(f'rule {index} has unsupported match shape {shape!r}')
        elif shape == 'literal':
            message = rule['message']
            if message in seen_literals:
                problems.append(
                    f'rule {index} repeats the literal {message!r} from rule '
                    f'{seen_literals[message]}; the first is unreachable'
                )
            seen_literals[message] = index
        elif shape == 'prefix':
            if not rule['prefix']:
                problems.append(f'rule {index} has an empty prefix, which matches everything')
        elif shape == 'regex':
            try:
                re.compile(rule['pattern'])
            except re.error as exc:
                problems.append(f'rule {index} has an invalid pattern: {exc}')
        if not rule.get('key'):
            problems.append(f'rule {index} has no key')
        runtime = rule.get('runtime')
        if not isinstance(runtime, dict):
            problems.append(f'rule {index} must declare runtime provenance')
        else:
            commands = runtime.get('commands')
            if commands != '*' and not (
                isinstance(commands, (list, tuple))
                and commands
                and all(isinstance(command, str) and command for command in commands)
            ):
                problems.append(f'rule {index} has invalid runtime commands')
            producer = runtime.get('producer')
            if (
                not isinstance(producer, dict)
                or producer.get('kind') not in ('command', 'helper')
                or not producer.get('name')
            ):
                problems.append(f'rule {index} has invalid runtime producer')
            if shape == 'regex' and not runtime.get('sample'):
                problems.append(f'rule {index} runtime regex has no concrete sample')
    return problems


def _unreachable(registry) -> list:
    """Rules shadowed by an earlier rule, reported with the rule that shadows."""
    shadowed = []
    for index, rule in enumerate(registry):
        if rule['match'] != 'prefix':
            continue
        for earlier in registry[:index]:
            if earlier['match'] == 'prefix' and rule['prefix'].startswith(earlier['prefix']):
                shadowed.append((index, earlier['prefix']))
                break
    return shadowed


def _runtime_scope_matches(rule, command):
    runtime = rule.get('runtime')
    if not isinstance(runtime, dict):
        return False
    commands = runtime.get('commands')
    return commands == '*' or (
        isinstance(commands, (list, tuple)) and command in commands
    )


def runtime_presentation_for(command, message):
    """Resolve one resident-runtime failure from the declarative runtime registry."""
    if not isinstance(message, str) or not message:
        return RUNTIME_FALLBACK_KEY, ()
    for rule in REGISTRY:
        if not _runtime_scope_matches(rule, command):
            continue
        shape = rule['match']
        if shape == 'literal':
            if message == rule['message']:
                return rule['key'], ()
            continue
        if shape == 'prefix':
            prefix = rule['prefix'].rstrip()
            if not message.startswith(prefix):
                continue
            remainder = message[len(prefix):].strip()
            arguments = (remainder,) if rule.get('argument') == 'remainder' else ()
            return rule['key'], arguments
        if shape == 'regex':
            match = re.match(rule['pattern'], message)
            if match is None:
                continue
            arguments = tuple(group or '' for group in match.groups())
            if rule.get('argument') == 'absent':
                arguments = ()
            return rule['key'], arguments
    return RUNTIME_FALLBACK_KEY, ()
