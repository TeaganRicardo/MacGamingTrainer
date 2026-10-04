"""Hades II player-facing error identity.

A user-facing failure must be readable in every supported language, but the
backend does not know the Host language. So a Hades-owned failure carries a
stable presentation *key* on the wire; the shipped bilingual tables
(`Sources/Hades2/Presentation/Localization/hades2.<lang>.json`) own the wording and
the Host resolves the key when it renders the message.

This is exactly the B02 split: `code` stays the stable machine identity,
`presentation` becomes a language-neutral key, and `diagnostic` keeps the
operator-readable detail. Core never learns a Hades term.

The Chinese text that used to be the raised message is retained as the
authoritative source for each key and is still surfaced through the diagnostic,
so the operator trace is unchanged while the wire stops being localized.
"""
import re
from dataclasses import dataclass, field
from typing import Optional, Sequence

from core.adapter import AdapterError


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



# ---------------------------------------------------------------------------
# The registry
# ---------------------------------------------------------------------------
#
# One list of rules replaces what used to be seven separate tables
# (`MESSAGE_KEYS`, `PREFIX_KEYS`, `REGEX_KEYS`, `ASSIGNED_KEYS`,
# `DELIMITED_AFFIX_KEYS`, `SEGMENTED_KEYS`, `DELIMITED_KEYS`) plus the
# `_ARGUMENT_KEYS` side-channel. That arrangement had a real cost: adding a
# player-facing message meant finding which of the seven tables owned its
# shape, adding a name to the list, and -- for prefix rules -- remembering a
# second table that decided whether the remainder travelled as an argument. The
# dispatch order was implicit in the table order and the argument convention was
# implicit in a frozenset.
#
# A rule now states all of it in one place: the shape it matches, the key it
# produces, and what becomes the argument. `shape` is declarative data, not a
# strategy object, so the whole registry is greppable, diffable and reviewable
# as one artefact.
#
# ORDER IS SEMANTIC. Rules are tried top to bottom and the first match wins,
# because a literal is more specific than a prefix, and a longer prefix is more
# specific than a shorter one that contains it. The list is therefore ordered by
# specificity, not grouped for readability: the `literal` rules come first, then
# the shapes in the order the previous dispatch used. `check_registry` reports a
# `prefix` rule that can never be reached because a longer `prefix` already
# covers it. The other shapes are not checked for shadowing: as of this writing
# no `affix`, `segmented` or `delimited` rule overlaps another of the same
# shape, and a shadowed one would still be caught by the behaviour snapshot.
#
# `argument` is explicit and optional:
#   "groups"    -> the regex capture groups, in order, absent ones kept as ''
#                 so a later value never shifts into the wrong placeholder
#   "remainder" -> whatever followed the matched prefix, kept whole, because
#                 splitting a composed message further would bake structure into
#                 a localized sentence
#   absent      -> the key takes no argument, even if the message had a suffix
#
# `composed` is provenance, not behaviour: it marks rules whose message is
# built into a local variable and only raised later, which a raise-site scan
# cannot see. The dispatcher ignores it; it is kept so that knowledge does not
# disappear with the tables.

REGISTRY = [
 {'match': 'literal',
  'message': '游戏内祝福菜单缺少受支持的关闭流程，无法安全继续修改。',
  'key': 'hades2.error.traitTrayCloseUnsupported'},
 {'match': 'literal',
  'message': '游戏内祝福菜单未能及时关闭，修改尚未执行。',
  'key': 'hades2.error.traitTrayCloseTimeout'},
 {'match': 'literal',
  'message': 'Selected boon is already owned',
  'key': 'hades2.error.exactAlreadyOwned',
  'runtime_only': True,
  'runtime': {'commands': ['spawn_reward'], 'producer': {'kind': 'command', 'name': 'spawn_reward'}}},
 {'match': 'literal',
  'message': 'Selected boon is not currently eligible',
  'key': 'hades2.error.exactNotEligible',
  'runtime_only': True,
  'runtime': {'commands': ['spawn_reward'], 'producer': {'kind': 'command', 'name': 'spawn_reward'}}},
 {'match': 'literal',
  'message': 'Selected boon became unavailable before acquisition',
  'key': 'hades2.error.exactNotEligible',
  'runtime_only': True,
  'runtime': {'commands': ['spawn_reward'], 'producer': {'kind': 'command', 'name': 'spawn_reward'}}},
 {'match': 'literal',
  'message': 'Echo previous-run boon is no longer eligible',
  'key': 'hades2.error.exactNotEligible',
  'runtime_only': True,
  'runtime': {'commands': ['spawn_reward'], 'producer': {'kind': 'command', 'name': 'spawn_reward'}}},
 {'match': 'literal',
  'message': 'Echo previous-run boon acquisition failed',
  'key': 'hades2.error.echoLastRunFailed',
  'runtime_only': True,
  'runtime': {'commands': ['spawn_reward'], 'producer': {'kind': 'helper', 'name': 'applyPreviousRunExact'}}},
 {'match': 'literal',
  'message': 'Trait mutation requires an active run room',
  'key': 'hades2.error.traitMutationNeedsRun',
  'runtime_only': True,
  'runtime': {'commands': ['set_trait_level', 'set_trait_rarity', 'set_trait_remaining_uses', 'expire_trait', 'remove_trait', 'advance_trait_lifecycle'], 'producer': {'kind': 'helper', 'name': 'resolveTraitTarget'}}},
 {'match': 'literal',
  'message': 'Trait selection belongs to a stale runtime generation',
  'key': 'hades2.error.traitSelectionStale',
  'runtime_only': True,
  'runtime': {'commands': ['set_trait_level', 'set_trait_rarity', 'set_trait_remaining_uses', 'expire_trait', 'remove_trait', 'advance_trait_lifecycle'], 'producer': {'kind': 'helper', 'name': 'resolveTraitTarget'}}},
 {'match': 'literal',
  'message': 'Trait selection belongs to a stale run',
  'key': 'hades2.error.traitSelectionStale',
  'runtime_only': True,
  'runtime': {'commands': ['set_trait_level', 'set_trait_rarity', 'set_trait_remaining_uses', 'expire_trait', 'remove_trait', 'advance_trait_lifecycle'], 'producer': {'kind': 'helper', 'name': 'resolveTraitTarget'}}},
 {'match': 'literal',
  'message': 'Trait instance is no longer present',
  'key': 'hades2.error.traitTargetMissing',
  'runtime_only': True,
  'runtime': {'commands': ['set_trait_level', 'set_trait_rarity', 'set_trait_remaining_uses', 'expire_trait', 'remove_trait', 'advance_trait_lifecycle'], 'producer': {'kind': 'helper', 'name': 'resolveTraitTarget'}}},
 {'match': 'literal',
  'message': 'Trait target changed since selection',
  'key': 'hades2.error.traitTargetChanged',
  'runtime_only': True,
  'runtime': {'commands': ['set_trait_level', 'set_trait_rarity', 'set_trait_remaining_uses', 'expire_trait', 'remove_trait', 'advance_trait_lifecycle'], 'producer': {'kind': 'helper', 'name': 'resolveTraitTarget'}}},
 {'match': 'literal',
  'message': 'Trait level editing is unavailable for the selected target',
  'key': 'hades2.error.traitLevelUnavailable',
  'runtime_only': True,
  'runtime': {'commands': ['set_trait_level'], 'producer': {'kind': 'command', 'name': 'set_trait_level'}}},
 {'match': 'literal',
  'message': 'Trait target level must be higher than the current level',
  'key': 'hades2.error.traitLevelTargetInvalid',
  'runtime_only': True,
  'runtime': {'commands': ['set_trait_level'], 'producer': {'kind': 'command', 'name': 'set_trait_level'}}},
 {'match': 'literal',
  'message': 'Trait is no longer eligible for a meaningful level increase',
  'key': 'hades2.error.traitLevelNoLongerEligible',
  'runtime_only': True,
  'runtime': {'commands': ['set_trait_level'], 'producer': {'kind': 'command', 'name': 'set_trait_level'}}},
 {'match': 'literal',
  'message': 'Trait level increase did not reach the requested target level',
  'key': 'hades2.error.traitLevelNoEffect',
  'runtime_only': True,
  'runtime': {'commands': ['set_trait_level'], 'producer': {'kind': 'command', 'name': 'set_trait_level'}}},
 {'match': 'literal',
  'message': 'Trait rarity editing is unavailable for the selected target',
  'key': 'hades2.error.traitRarityUnavailable',
  'runtime_only': True,
  'runtime': {'commands': ['set_trait_rarity'], 'producer': {'kind': 'command', 'name': 'set_trait_rarity'}}},
 {'match': 'literal',
  'message': 'Trait rarity recompute did not reach the requested rarity',
  'key': 'hades2.error.traitRarityNoEffect',
  'runtime_only': True,
  'runtime': {'commands': ['set_trait_rarity'], 'producer': {'kind': 'command', 'name': 'set_trait_rarity'}}},
 {'match': 'literal',
  'message': 'Trait removal is unavailable for the selected target',
  'key': 'hades2.error.traitRemovalUnavailable',
  'runtime_only': True,
  'runtime': {'commands': ['remove_trait'], 'producer': {'kind': 'command', 'name': 'remove_trait'}}},
 {'match': 'literal',
  'message': 'Trait removal capability is unknown',
  'key': 'hades2.error.traitRemovalCapabilityUnknown',
  'runtime_only': True,
  'runtime': {'commands': ['remove_trait'], 'producer': {'kind': 'command', 'name': 'remove_trait'}}},
 {'match': 'literal',
  'message': 'Native trait removal left a matching instance mounted',
  'key': 'hades2.error.traitRemovalNoEffect',
  'runtime_only': True,
  'runtime': {'commands': ['remove_trait'], 'producer': {'kind': 'command', 'name': 'remove_trait'}}},
 {'match': 'literal',
  'message': 'Direct trait removal left the selected instance mounted',
  'key': 'hades2.error.traitRemovalNoEffect',
  'runtime_only': True,
  'runtime': {'commands': ['remove_trait'], 'producer': {'kind': 'command', 'name': 'remove_trait'}}},
 {'match': 'literal',
  'message': 'Temporary effect duration editing is unavailable for the selected target',
  'key': 'hades2.error.traitDurationUnavailable',
  'runtime_only': True,
  'runtime': {'commands': ['set_trait_remaining_uses'], 'producer': {'kind': 'command', 'name': 'set_trait_remaining_uses'}}},
 {'match': 'literal',
  'message': 'Temporary effect duration did not reach the requested remaining uses',
  'key': 'hades2.error.traitDurationNoEffect',
  'runtime_only': True,
  'runtime': {'commands': ['set_trait_remaining_uses', 'expire_trait'], 'producer': {'kind': 'helper', 'name': 'setCounter'}}},
 {'match': 'literal',
  'message': 'Temporary effect expiry is unavailable for the selected target',
  'key': 'hades2.error.traitExpiryUnavailable',
  'runtime_only': True,
  'runtime': {'commands': ['expire_trait'], 'producer': {'kind': 'command', 'name': 'expire_trait'}}},
 {'match': 'literal',
  'message': 'Temporary effect expiry left the selected instance mounted',
  'key': 'hades2.error.traitRemovalNoEffect',
  'runtime_only': True,
  'runtime': {'commands': ['expire_trait'], 'producer': {'kind': 'helper', 'name': 'expire'}}},
 {'match': 'literal',
  'message': 'Temporary effect cancellation left the selected instance mounted',
  'key': 'hades2.error.traitRemovalNoEffect',
  'runtime_only': True,
  'runtime': {'commands': ['remove_trait'], 'producer': {'kind': 'helper', 'name': 'cancel'}}},
 {'match': 'literal',
  'message': 'Familiar owner removal is unavailable',
  'key': 'hades2.error.traitRemovalUnavailable',
  'runtime_only': True,
  'runtime': {'commands': ['remove_trait'], 'producer': {'kind': 'helper', 'name': 'teardownOwner'}}},
 {'match': 'literal',
  'message': 'Familiar owner removal left a mounted trait',
  'key': 'hades2.error.traitRemovalNoEffect',
  'runtime_only': True,
  'runtime': {'commands': ['remove_trait'], 'producer': {'kind': 'helper', 'name': 'teardownOwner'}}},
 {'match': 'literal',
  'message': 'Familiar owner removal left the owner equipped',
  'key': 'hades2.error.traitRemovalNoEffect',
  'runtime_only': True,
  'runtime': {'commands': ['remove_trait'], 'producer': {'kind': 'helper', 'name': 'teardownOwner'}}},
 {'match': 'literal',
  'message': 'Keepsake owner removal is unavailable',
  'key': 'hades2.error.traitRemovalUnavailable',
  'runtime_only': True,
  'runtime': {'commands': ['remove_trait'], 'producer': {'kind': 'helper', 'name': 'teardownOwner'}}},
 {'match': 'literal',
  'message': 'Keepsake owner removal left the selected trait mounted',
  'key': 'hades2.error.traitRemovalNoEffect',
  'runtime_only': True,
  'runtime': {'commands': ['remove_trait'], 'producer': {'kind': 'helper', 'name': 'teardownOwner'}}},
 {'match': 'literal',
  'message': 'Chaos trait editing is unavailable',
  'key': 'hades2.error.chaosTraitEditUnavailable',
  'runtime_only': True,
  'runtime': {'commands': ['set_trait_level', 'set_trait_rarity'], 'producer': {'kind': 'helper', 'name': 'rebuildChaosTarget'}}},
 {'match': 'literal',
  'message': 'Chaos trait edit failed',
  'key': 'hades2.error.chaosTraitEditFailed',
  'runtime_only': True,
  'runtime': {'commands': ['set_trait_level', 'set_trait_rarity'], 'producer': {'kind': 'helper', 'name': 'rebuildChaosTarget'}}},
 {'match': 'literal',
  'message': 'Chaos lifecycle transition is unavailable',
  'key': 'hades2.error.chaosLifecycleUnavailable',
  'runtime_only': True,
  'runtime': {'commands': ['advance_trait_lifecycle'], 'producer': {'kind': 'command', 'name': 'advance_trait_lifecycle'}}},
 {'match': 'literal',
  'message': 'Chaos lifecycle transition failed',
  'key': 'hades2.error.chaosLifecycleFailed',
  'runtime_only': True,
  'runtime': {'commands': ['advance_trait_lifecycle'], 'producer': {'kind': 'command', 'name': 'advance_trait_lifecycle'}}},
 {'match': 'literal',
  'message': 'Chaos exact acquisition is unavailable',
  'key': 'hades2.error.chaosExactUnavailable',
  'runtime_only': True,
  'runtime': {'commands': ['spawn_reward'], 'producer': {'kind': 'command', 'name': 'spawn_reward'}}},
 {'match': 'literal',
  'message': 'Chaos exact acquisition failed',
  'key': 'hades2.error.chaosExactFailed',
  'runtime_only': True,
  'runtime': {'commands': ['spawn_reward'], 'producer': {'kind': 'command', 'name': 'spawn_reward'}}},
 {'match': 'literal',
  'message': 'Selene spell target is unavailable',
  'key': 'hades2.error.exactNotEligible',
  'runtime_only': True,
  'runtime': {'commands': ['spawn_reward'], 'producer': {'kind': 'command', 'name': 'spawn_reward'}}},
 {'match': 'literal',
  'message': 'Selene talent is unavailable for the current Path of Stars',
  'key': 'hades2.error.exactNotEligible',
  'runtime_only': True,
  'runtime': {'commands': ['spawn_reward'], 'producer': {'kind': 'command', 'name': 'spawn_reward'}}},
 {'match': 'literal',
  'message': 'Selene talent is no longer available in the current Path of Stars',
  'key': 'hades2.error.exactNotEligible',
  'runtime_only': True,
  'runtime': {'commands': ['spawn_reward'], 'producer': {'kind': 'helper', 'name': 'applyTalent'}}},
 {'match': 'literal',
  'message': 'Mounted Selene talent is unavailable',
  'key': 'hades2.error.exactNotEligible',
  'runtime_only': True,
  'runtime': {'commands': ['spawn_reward'], 'producer': {'kind': 'helper', 'name': 'applyTalent'}}},
 {'match': 'literal',
  'message': 'Selene spell acquisition failed',
  'key': 'hades2.error.seleneExactFailed',
  'runtime_only': True,
  'runtime': {'commands': ['spawn_reward'], 'producer': {'kind': 'helper', 'name': 'applySpell'}}},
 {'match': 'literal',
  'message': 'Selene talent acquisition failed',
  'key': 'hades2.error.seleneExactFailed',
  'runtime_only': True,
  'runtime': {'commands': ['spawn_reward'], 'producer': {'kind': 'helper', 'name': 'applyTalent'}}},
 {'match': 'literal',
  'message': 'Not enough uninvested Path of Stars nodes remain for the requested level',
  'key': 'hades2.error.traitLevelNoLongerEligible',
  'runtime_only': True,
  'runtime': {'commands': ['set_trait_level'], 'producer': {'kind': 'command', 'name': 'set_trait_level'}}},
 {'match': 'literal',
  'message': 'Selene talent tree changed before the requested level was applied',
  'key': 'hades2.error.traitTargetChanged',
  'runtime_only': True,
  'runtime': {'commands': ['set_trait_level'], 'producer': {'kind': 'command', 'name': 'set_trait_level'}}},
 {'match': 'literal',
  'message': 'Selene spell removal left owner state mounted',
  'key': 'hades2.error.traitRemovalNoEffect',
  'runtime_only': True,
  'runtime': {'commands': ['remove_trait'], 'producer': {'kind': 'command', 'name': 'remove_trait'}}},
 {'match': 'literal',
  'message': 'Selene talent removal left the mounted effect present',
  'key': 'hades2.error.traitRemovalNoEffect',
  'runtime_only': True,
  'runtime': {'commands': ['remove_trait'], 'producer': {'kind': 'command', 'name': 'remove_trait'}}},
 {'match': 'literal',
  'message': 'Exact costume target is unavailable',
  'key': 'hades2.error.exactNotEligible',
  'runtime_only': True,
  'runtime': {'commands': ['spawn_reward'], 'producer': {'kind': 'command', 'name': 'spawn_reward'}}},
 {'match': 'literal',
  'message': 'Arachne costume acquisition failed',
  'key': 'hades2.error.costumeOwnerFailed',
  'runtime_only': True,
  'runtime': {'commands': ['spawn_reward'], 'producer': {'kind': 'helper', 'name': 'applyCostume'}}},
 {'match': 'literal',
  'message': 'Arachne costume replacement left previous owner mounted',
  'key': 'hades2.error.costumeOwnerFailed',
  'runtime_only': True,
  'runtime': {'commands': ['spawn_reward'], 'producer': {'kind': 'helper', 'name': 'applyCostume'}}},
 {'match': 'literal',
  'message': 'Arachne costume removal left owner state mounted',
  'key': 'hades2.error.traitRemovalNoEffect',
  'runtime_only': True,
  'runtime': {'commands': ['remove_trait'], 'producer': {'kind': 'helper', 'name': 'removeCostume'}}},
 {'match': 'literal',
  'message': 'Cannot open boon sell screen while another screen is active',
  'key': 'hades2.error.sellScreenBusy',
  'runtime_only': True,
  'runtime': {'commands': ['open_sell_traits'], 'producer': {'kind': 'command', 'name': 'open_sell_traits'}}},
 {'match': 'literal',
  'message': 'Boon selling requires an active run room',
  'key': 'hades2.error.sellNeedsRunRoom',
  'runtime_only': True,
  'runtime': {'commands': ['open_sell_traits'], 'producer': {'kind': 'command', 'name': 'open_sell_traits'}}},
 {'match': 'literal',
  'message': 'Native boon sell screen data is unavailable',
  'key': 'hades2.error.sellDataUnavailable',
  'runtime_only': True,
  'runtime': {'commands': ['open_sell_traits'], 'producer': {'kind': 'command', 'name': 'open_sell_traits'}}},
 {'match': 'literal',
  'message': 'Action requires a requestId of 1..128 characters',
  'key': 'hades2.error.requestIdRequired',
  'runtime_only': True,
  'runtime': {'commands': ['set_trait_level', 'set_trait_rarity', 'set_trait_remaining_uses', 'expire_trait', 'remove_trait', 'advance_trait_lifecycle'], 'producer': {'kind': 'helper', 'name': 'action'}}},
 {'match': 'literal',
  'message': 'requestId reused for a different action',
  'key': 'hades2.error.requestIdReused',
  'runtime_only': True,
  'runtime': {'commands': ['set_trait_level', 'set_trait_rarity', 'set_trait_remaining_uses', 'expire_trait', 'remove_trait', 'advance_trait_lifecycle'], 'producer': {'kind': 'helper', 'name': 'action'}}},
 {'match': 'literal',
  'message': 'MGT_OUTCOME_UNKNOWN: Previous action outcome is unknown; do not retry',
  'key': 'hades2.error.outcomeUnknownRuntime',
  'runtime_only': True,
  'runtime': {'commands': ['set_trait_level', 'set_trait_rarity', 'set_trait_remaining_uses', 'expire_trait', 'remove_trait', 'advance_trait_lifecycle'], 'producer': {'kind': 'helper', 'name': 'action'}}},
 {'match': 'literal',
  'message': 'Cannot open special blessing choice while another screen is active',
  'key': 'hades2.error.choiceScreenBusy',
  'runtime_only': True,
  'runtime': {'commands': ['open_special_choice'], 'producer': {'kind': 'command', 'name': 'open_special_choice'}}},
 {'match': 'literal',
  'message': 'Cannot open special blessing choice during a transition',
  'key': 'hades2.error.choiceDuringTransition',
  'runtime_only': True,
  'runtime': {'commands': ['open_special_choice'], 'producer': {'kind': 'command', 'name': 'open_special_choice'}}},
 {'match': 'literal',
  'message': 'Special blessing choice requires an active run room',
  'key': 'hades2.error.choiceNeedsRunRoom',
  'runtime_only': True,
  'runtime': {'commands': ['open_special_choice'], 'producer': {'kind': 'command', 'name': 'open_special_choice'}}},
 {'match': 'literal',
  'message': 'Special blessing source has no audited native choice flow',
  'key': 'hades2.error.choiceNoAuditedFlow',
  'runtime_only': True,
  'runtime': {'commands': ['open_special_choice'], 'producer': {'kind': 'command', 'name': 'open_special_choice'}}},
 {'match': 'literal',
  'message': 'Special blessing source data is unavailable',
  'key': 'hades2.error.choiceSourceUnavailable',
  'runtime_only': True,
  'runtime': {'commands': ['open_special_choice'], 'producer': {'kind': 'command', 'name': 'open_special_choice'}}},
 {'match': 'literal',
  'message': 'Special blessing choice data is unavailable',
  'key': 'hades2.error.choiceDataUnavailable',
  'runtime_only': True,
  'runtime': {'commands': ['open_special_choice'], 'producer': {'kind': 'command', 'name': 'open_special_choice'}}},
 {'match': 'literal',
  'message': 'No eligible special blessings are available',
  'key': 'hades2.error.noEligibleSpecialRewards',
  'runtime_only': True,
  'runtime': {'commands': ['open_special_choice'], 'producer': {'kind': 'command', 'name': 'open_special_choice'}}},
 {'match': 'regex',
  'pattern': r'^Unsupported (?P<purpose>.+?): missing (?P<missing>.+)$',
  'key': 'hades2.error.nativeFunctionMissing',
  'argument': 'groups',
  'runtime_only': True,
  'runtime': {'commands': '*',
              'producer': {'kind': 'helper', 'name': 'requireFunctions'},
              'sample': 'Unsupported sample-purpose: missing SampleFunction'}},
 {'match': 'literal',
  'message': 'Legendary / Duo 设置无效。',
  'key': 'hades2.error.invalidLegendaryDuo'},
 {'match': 'literal', 'message': 'Lua 执行失败', 'key': 'hades2.error.luaFailed'},
 {'match': 'literal',
  'message': 'Profile desired 字段无效。',
  'key': 'hades2.error.profileDesiredInvalid'},
 {'match': 'literal',
  'message': 'Profile desiredSchemaVersion 无效。',
  'key': 'hades2.error.profileDesiredSchemaInvalid'},
 {'match': 'literal',
  'message': 'Profile schemaVersion 无效。',
  'key': 'hades2.error.profileSchemaInvalid'},
 {'match': 'literal',
  'message': 'Profile shortcuts 字段无效。',
  'key': 'hades2.error.profileShortcutsInvalid'},
 {'match': 'literal',
  'message': 'Profile updatedAt 字段无效。',
  'key': 'hades2.error.profileUpdatedAtInvalid'},
 {'match': 'literal',
  'message': 'Profile updatedAt 字段缺失。',
  'key': 'hades2.error.profileUpdatedAtMissing'},
 {'match': 'literal',
  'message': 'Profile 包含当前 schema 未定义的顶层字段。',
  'key': 'hades2.error.profileUnknownFields'},
 {'match': 'literal',
  'message': 'Profile 名称不能包含路径分隔符。',
  'key': 'hades2.error.profileNameSeparator'},
 {'match': 'literal',
  'message': 'Profile 名称与文件标识不一致。',
  'key': 'hades2.error.profileNameIdentifierMismatch'},
 {'match': 'literal',
  'message': 'Profile 名称必须为 1–64 个可见字符。',
  'key': 'hades2.error.profileNameLength'},
 {'match': 'literal', 'message': 'Profile 名称无效。', 'key': 'hades2.error.profileNameInvalid'},
 {'match': 'literal',
  'message': 'Profile 名称未规范化。',
  'key': 'hades2.error.profileNameNotNormalized'},
 {'match': 'literal', 'message': 'Profile 文件已损坏。', 'key': 'hades2.error.profileCorrupt'},
 {'match': 'literal',
  'message': 'desired-state schemaVersion 无效。',
  'key': 'hades2.error.desiredSchemaInvalid'},
 {'match': 'literal',
  'message': 'probeRuntime 必须为布尔值。',
  'key': 'hades2.error.probeRuntimeBoolean'},
 {'match': 'literal',
  'message': 'runtime observation 仅允许 status。',
  'key': 'hades2.error.runtimeObservationOnly'},
 {'match': 'literal', 'message': '上次调用结果不明，请重启游戏后重新连接。', 'key': 'hades2.error.restartRequired'},
 {'match': 'literal', 'message': '下一房奖励无效。', 'key': 'hades2.error.invalidNextRoomReward'},
 {'match': 'literal', 'message': '使用新的数据格式', 'key': 'hades2.error.preferenceNewerFormat'},
 {'match': 'literal', 'message': '倍率必须为有限数值。', 'key': 'hades2.error.multiplierFinite'},
 {'match': 'literal', 'message': '倍率范围为 1–100。', 'key': 'hades2.error.multiplierRange'},
 {'match': 'literal', 'message': '元素数量必须为 0–', 'key': 'hades2.error.elementRange'},
 {'match': 'literal', 'message': '功能代码过长。', 'key': 'hades2.error.featureCodeTooLong'},
 {'match': 'literal', 'message': '原始备份损坏或与记录不匹配；拒绝覆盖游戏。', 'key': 'hades2.error.backupCorrupt'},
 {'match': 'literal',
  'message': '原始恢复副本 UUID 不匹配；未修改游戏。',
  'key': 'hades2.error.restoreUUIDMismatch'},
 {'match': 'literal', 'message': '参数类型不支持。', 'key': 'hades2.error.invalidParamsObject'},
 {'match': 'literal',
  'message': '后台暂停标志尚未恢复，请保持连接重试断开。',
  'key': 'hades2.error.focusNotRestored'},
 {'match': 'literal', 'message': '后台暂停标志恢复校验失败。', 'key': 'hades2.error.focusRestoreMismatch'},
 {'match': 'literal', 'message': '后台运行标志无法验证。', 'key': 'hades2.error.runFlagUnverifiable'},
 {'match': 'literal', 'message': '备份 UUID 不匹配。', 'key': 'hades2.error.backupUUIDMismatch'},
 {'match': 'literal', 'message': '局内数值字段无效。', 'key': 'hades2.error.vitalField'},
 {'match': 'literal', 'message': '局内数值必须为 0–', 'key': 'hades2.error.vitalRange'},
 {'match': 'literal', 'message': '属性值必须为有限数值。', 'key': 'hades2.error.statFinite'},
 {'match': 'literal', 'message': '巫咒充能必须为 0–', 'key': 'hades2.error.spellChargeRange'},
 {'match': 'literal', 'message': '已准备文件缺少调试权限。', 'key': 'hades2.error.missingDebugPermission'},
 {'match': 'literal', 'message': '开关值必须为布尔值。', 'key': 'hades2.error.featureToggleBoolean'},
 {'match': 'literal',
  'message': '当前可执行文件已带调试权限，但没有匹配的原始备份；拒绝覆盖。',
  'key': 'hades2.error.noMatchingBackup'},
 {'match': 'literal', 'message': '必须输入有限数值。', 'key': 'hades2.error.statFinite'},
 {'match': 'literal', 'message': '悟性上限必须是 0–999 的整数。', 'key': 'hades2.error.graspRange'},
 {'match': 'literal', 'message': '护甲仅提供当前值，不存在可编辑上限。', 'key': 'hades2.error.armorNoMaximum'},
 {'match': 'literal',
  'message': '损坏的 desired-state 无法安全隔离，已禁止覆盖原文件。',
  'key': 'hades2.error.preferenceWriteBlocked'},
 {'match': 'literal', 'message': '敌人伤害倍率必须为 0–1000%。', 'key': 'hades2.error.enemyDamageRange'},
 {'match': 'literal', 'message': '敌人生命倍率必须为 10–1000%。', 'key': 'hades2.error.enemyHealthRange'},
 {'match': 'literal', 'message': '数量必须是 0–', 'key': 'hades2.error.amountRange'},
 {'match': 'literal', 'message': '无法在时限内暂停游戏。', 'key': 'hades2.error.pauseFailed'},
 {'match': 'literal', 'message': '无法安全写入本地配置。', 'key': 'hades2.error.localWriteFailed'},
 {'match': 'literal', 'message': '无法定位游戏镜像。', 'key': 'hades2.error.imageNotFound'},
 {'match': 'literal',
  'message': '无法读取原始权限；未修改游戏。',
  'key': 'hades2.error.permissionsUnreadable'},
 {'match': 'literal',
  'message': '无法读取操作结果；请检查游戏，不要重复资源操作。',
  'key': 'hades2.error.outcomeUnknownUnreadable'},
 {'match': 'literal',
  'message': '暂存文件校验失败；未修改游戏。',
  'key': 'hades2.error.stagedVerificationFailed'},
 {'match': 'literal', 'message': '目标等级必须高于当前等级。', 'key': 'hades2.error.traitLevelTargetInvalid'},
 {'match': 'literal', 'message': '最低稀有度无效。', 'key': 'hades2.error.invalidRarityTarget'},
 {'match': 'literal', 'message': '未找到该 Profile。', 'key': 'hades2.error.profileNotFound'},
 {'match': 'literal', 'message': '未知元素。', 'key': 'hades2.error.unknownElement'},
 {'match': 'literal', 'message': '未知功能。', 'key': 'hades2.error.unknownFeature'},
 {'match': 'literal', 'message': '未知命令。', 'key': 'hades2.error.invalidCommand'},
 {'match': 'literal', 'message': '未知局内数值。', 'key': 'hades2.error.unknownVital'},
 {'match': 'literal', 'message': '未知局内计数器。', 'key': 'hades2.error.unknownCounter'},
 {'match': 'literal', 'message': '未知属性。', 'key': 'hades2.error.unknownStat'},
 {'match': 'literal', 'message': '未知错误', 'key': 'hades2.error.unknownDetail'},
 {'match': 'literal', 'message': '概率必须为 0–100。', 'key': 'hades2.error.percentRange'},
 {'match': 'literal',
  'message': '没有与当前文件匹配的原始签名备份；游戏可能已更新，拒绝覆盖。',
  'key': 'hades2.error.noOriginalBackup'},
 {'match': 'literal', 'message': '游戏内操作失败，请查看日志。', 'key': 'hades2.error.runtimeActionFailed'},
 {'match': 'literal', 'message': '游戏发生非预期停顿，已停止当前操作。', 'key': 'hades2.error.unexpectedStop'},
 {'match': 'literal', 'message': '游戏已退出或连接已断开。', 'key': 'hades2.error.notAttached'},
 {'match': 'literal',
  'message': '游戏文件在操作期间改变；拒绝覆盖。',
  'key': 'hades2.error.fileChangedDuringOperation'},
 {'match': 'literal', 'message': '游戏未能恢复运行。', 'key': 'hades2.error.resumeUnverified'},
 {'match': 'literal', 'message': '游戏调用结果不明，未自动重试。', 'key': 'hades2.error.outcomeUnknownEmpty'},
 {'match': 'literal',
  'message': '游戏调用结果不明，未自动重试；请检查游戏并重启。',
  'key': 'hades2.error.outcomeUnknownGeneric'},
 {'match': 'literal', 'message': '游戏进程已结束。', 'key': 'hades2.error.processExited'},
 {'match': 'literal', 'message': '游戏进程已退出。', 'key': 'hades2.error.processExitedSecond'},
 {'match': 'literal', 'message': '游戏进程状态切换超时。', 'key': 'hades2.error.processTimeout'},
 {'match': 'literal', 'message': '游戏速度范围为 0–10。', 'key': 'hades2.error.gameSpeedRange'},
 {'match': 'literal', 'message': '独立验证副本校验失败；未修改游戏。', 'key': 'hades2.error.verificationFailed'},
 {'match': 'literal',
  'message': '现有 desired-state 无法安全读取，已禁止本次进程覆盖原文件。',
  'key': 'hades2.error.preferenceWriteBlocked'},
 {'match': 'literal',
  'message': '现有 desired-state 无法安全隔离，已禁止覆盖原文件。',
  'key': 'hades2.error.preferenceWriteBlocked'},
 {'match': 'literal', 'message': '生命值必须至少为 1。', 'key': 'hades2.error.healthMinimum'},
 {'match': 'literal',
  'message': '稀有度倍率必须为 0–1000%。',
  'key': 'hades2.error.invalidRarityMultiplier'},
 {'match': 'literal',
  'message': '等待游戏世界更新超时。请进入存档并关闭暂停菜单后重试。',
  'key': 'hades2.error.worldUpdateTimeout'},
 {'match': 'literal', 'message': '请先连接游戏。', 'key': 'hades2.error.notConnected'},
 {'match': 'literal',
  'message': '请断开连接并退出游戏后操作。',
  'key': 'hades2.error.disconnectBeforePrepare'},
 {'match': 'literal', 'message': '请选择掉落物或祝福。', 'key': 'hades2.error.selectReward'},
 {'match': 'literal', 'message': '请选择支持原生奖励选择界面的角色。', 'key': 'hades2.error.selectChoiceSource'},
 {'match': 'literal', 'message': '请选择当前局祝福。', 'key': 'hades2.error.selectCurrentTrait'},
 {'match': 'literal', 'message': '请选择当前局效果。', 'key': 'hades2.error.selectCurrentTrait'},
 {'match': 'literal', 'message': '剩余次数必须为 1–999999 的整数。', 'key': 'hades2.error.remainingUsesRange'},
 {'match': 'literal', 'message': '请选择资源。', 'key': 'hades2.error.selectResource'},
 {'match': 'literal',
  'message': '调试签名校验失败；未修改游戏。',
  'key': 'hades2.error.signingVerificationFailed'},
 {'match': 'literal',
  'message': '速度倍率必须为 10–1000%。',
  'key': 'hades2.error.speedMultiplierRange'},
 {'match': 'literal', 'message': '锁定值必须为布尔值。', 'key': 'hades2.error.lockedBoolean'},
 {'match': 'literal', 'message': '额外魔力恢复必须为 0–1000/秒。', 'key': 'hades2.error.manaRegenRange'},
 {'match': 'regex',
  'pattern': '^(?P<game>.+?) 适配器需要 (?P<requirement>.+?) 原生游戏。$',
  'key': 'hades2.error.architectureRequired',
  'argument': 'groups'},
 {'match': 'regex',
  'pattern': '^连接被拒绝：(?P<detail>.+?)。退出游戏后使用',
  'key': 'hades2.error.attachDenied',
  'argument': 'groups'},
 {'match': 'regex',
  'pattern': '^找不到匹配架构的 Mach-O UUID\\s*(?P<suffix>[^\\s，。]*)?。?$',
  'key': 'hades2.error.uuidLookupFailed',
  'argument': 'groups'},
 {'match': 'regex',
  'pattern': '^未从本机 (?P<game>.+?) 中文语言文件解析到 (?P<count>.+?) 项',
  'key': 'hades2.error.missingOfficialNames',
  'argument': 'groups'},
 {'match': 'regex',
  'pattern': '^(?P<tool>.+?) 失败（(?P<returncode>.+?)）：(?P<detail>.+)$',
  'key': 'hades2.error.commandFailed',
  'argument': 'groups'},
 {'match': 'regex',
  'pattern': '^(?P<tool>.+?) 超时（(?P<timeout>.+?) 秒）；',
  'key': 'hades2.error.timeout',
  'argument': 'groups'},
 {'match': 'regex',
  'pattern': '^请先退出 (?P<game>.+?)；',
  'key': 'hades2.error.prepareWhileRunning',
  'argument': 'groups'},
 {'match': 'regex',
  'pattern': '^未经验证的游戏版本：version=(?P<version>.*?), build=(?P<build>.*?), UUID=(?P<uuid>.*?)。$',
  'key': 'hades2.error.unverifiedBuildWarning',
  'argument': 'groups'},
 {'match': 'regex',
  'pattern': '^无法运行 (?P<tool>[^：]+)：(?P<detail>.+)$',
  'key': 'hades2.error.commandLaunchFailed',
  'argument': 'groups'},
 {'match': 'regex',
  'pattern': '^(?P<kind>.+?) 使用了更新的数据格式（schemaVersion=(?P<found>[^，]*)，当前支持 '
             '(?P<supported>[^）]*)），',
  'key': 'hades2.error.preferenceNewerFormat',
  'argument': 'groups',
  'composed': 'raised_later'},
 {'match': 'regex',
  'pattern': '^(?P<kind>.+?) 使用了已不再支持的旧数据格式（schemaVersion=(?P<found>[^，]*)，当前支持 '
             '(?P<supported>[^）]*)），',
  'key': 'hades2.error.preferenceOlderFormat',
  'argument': 'groups',
  'composed': 'raised_later'},
 {'match': 'affix',
  'prefix': '请先启动',
  'suffix': ' 并进入存档。',
  'key': 'hades2.error.gameNotRunning'},
 {'match': 'affix',
  'prefix': '检测到多个',
  'suffix': ' 进程，请保留一个。',
  'key': 'hades2.error.multipleProcesses'},
 {'match': 'segmented',
  'prefix': '查询',
  'separator': ' 进程失败（',
  'terminator': '）：',
  'key': 'hades2.error.processQueryFailed'},
 {'match': 'prefix',
  'prefix': '请先启动 ',
  'key': 'hades2.error.gameNotRunning',
  'argument': 'remainder'},
 {'match': 'prefix',
  'prefix': '查询 ',
  'key': 'hades2.error.processQueryFailed',
  'argument': 'remainder'},
 {'match': 'prefix',
  'prefix': '连接被拒绝：',
  'key': 'hades2.error.attachDenied',
  'argument': 'remainder'},
 {'match': 'prefix',
  'prefix': '缺少符号：',
  'key': 'hades2.error.missingSymbol',
  'argument': 'remainder'},
 {'match': 'prefix',
  'prefix': '新版本关键符号无法唯一定位：',
  'key': 'hades2.error.symbolNotUnique',
  'argument': 'remainder'},
 {'match': 'prefix',
  'prefix': '新版本关键符号不可读：',
  'key': 'hades2.error.symbolUnreadable',
  'argument': 'remainder'},
 {'match': 'prefix',
  'prefix': '运行中的游戏函数校验失败：',
  'key': 'hades2.error.runtimeVerificationFailed',
  'argument': 'remainder'},
 {'match': 'prefix',
  'prefix': '无法恢复游戏运行：',
  'key': 'hades2.error.resumeFailed',
  'argument': 'remainder'},
 {'match': 'prefix',
  'prefix': '后台暂停标志恢复失败：',
  'key': 'hades2.error.focusRestoreFailed',
  'argument': 'remainder'},
 {'match': 'prefix',
  'prefix': '请先退出 ',
  'key': 'hades2.error.prepareWhileRunning',
  'argument': 'remainder'},
 {'match': 'prefix',
  'prefix': '无法运行 ',
  'key': 'hades2.error.commandLaunchFailed',
  'argument': 'remainder'},
 {'match': 'prefix',
  'prefix': '游戏调用结果不明，未自动重试：',
  'key': 'hades2.error.outcomeUnknownTransport',
  'argument': 'remainder'},
 {'match': 'prefix',
  'prefix': '未经验证的游戏版本：',
  'key': 'hades2.error.unverifiedBuildWarning',
  'argument': 'remainder'},
 {'match': 'prefix',
  'prefix': '未从本机 ',
  'key': 'hades2.error.missingOfficialNames',
  'argument': 'remainder'},
 {'match': 'delimited',
  'open': '元素数量必须为 0–',
  'close': ' 的整数。',
  'key': 'hades2.error.elementRange'},
 {'match': 'delimited', 'open': '局内数值必须为 0–', 'close': '。', 'key': 'hades2.error.vitalRange'},
 {'match': 'delimited',
  'open': '巫咒充能必须为 0–',
  'close': '。',
  'key': 'hades2.error.spellChargeRange'},
 {'match': 'delimited',
  'open': '数量必须是 0–',
  'close': ' 的整数。',
  'key': 'hades2.error.amountRange'},
 {'match': 'delimited', 'open': ' 失败（', 'close': '）', 'key': 'hades2.error.commandFailed'},
 {'match': 'delimited', 'open': ' 超时（', 'close': ' 秒）', 'key': 'hades2.error.timeout'}]
RUNTIME_FALLBACK_KEY = 'hades2.error.runtimeActionFailed'

# Compile the regex rules once, at import, and keep the pattern text alongside
# so a failure can name the rule that produced it.
_COMPILED = [
    (index, re.compile(rule["pattern"]), rule)
    for index, rule in enumerate(REGISTRY)
    if rule["match"] == "regex" and not rule.get("runtime_only")
]
_LITERALS = {}
for _rule in REGISTRY:
    if _rule["match"] == "literal" and not _rule.get("runtime_only"):
        # A duplicate literal would make the first one unreachable. check_registry
        # rejects it, and this keeps the last-wins behaviour impossible to rely
        # on even if that check is bypassed.
        _LITERALS[_rule["message"]] = _rule["key"]


def check_registry(registry=None) -> list:
    """Return the structural problems in the registry, if any.

    An unreachable rule is a rule that can never fire: its shape is fully
    shadowed by an earlier rule. That is almost always a mistake, and it would
    be invisible in the dispatch code, which is exactly why it is checked here.
    """
    registry = REGISTRY if registry is None else registry
    problems = []
    seen_literals = {}
    for index, rule in enumerate(registry):
        shape = rule.get("match")
        if shape == "literal":
            message = rule["message"]
            if message in seen_literals:
                problems.append(
                    f"rule {index} repeats the literal {message!r} from rule "
                    f"{seen_literals[message]}; the first is unreachable")
            seen_literals[message] = index
        elif shape == "prefix":
            if not rule["prefix"]:
                problems.append(f"rule {index} has an empty prefix, which matches everything")
        elif shape == "regex":
            try:
                re.compile(rule["pattern"])
            except re.error as exc:
                problems.append(f"rule {index} has an invalid pattern: {exc}")
        for field_name in ("key",):
            if not rule.get(field_name):
                problems.append(f"rule {index} has no {field_name}")
        runtime = rule.get("runtime")
        if runtime is not None:
            if not isinstance(runtime, dict):
                problems.append(f"rule {index} runtime metadata must be an object")
            else:
                commands = runtime.get("commands")
                if commands != "*" and not (
                    isinstance(commands, (list, tuple)) and commands
                    and all(isinstance(command, str) and command for command in commands)
                ):
                    problems.append(f"rule {index} has invalid runtime commands")
                producer = runtime.get("producer")
                if not isinstance(producer, dict) or producer.get("kind") not in ("command", "helper") or not producer.get("name"):
                    problems.append(f"rule {index} has invalid runtime producer")
                if shape == "regex" and not runtime.get("sample"):
                    problems.append(f"rule {index} runtime regex has no concrete sample")
    return problems


def _unreachable(registry) -> list:
    """Rules shadowed by an earlier rule, reported with the rule that shadows."""
    shadowed = []
    for index, rule in enumerate(registry):
        if rule["match"] != "prefix":
            continue
        for earlier in registry[:index]:
            if earlier["match"] == "prefix" and rule["prefix"].startswith(earlier["prefix"]):
                shadowed.append((index, earlier["prefix"]))
                break
    return shadowed



def _runtime_scope_matches(rule, command):
    runtime = rule.get("runtime")
    if not isinstance(runtime, dict):
        return False
    commands = runtime.get("commands")
    return commands == "*" or (
        isinstance(commands, (list, tuple)) and command in commands
    )


def runtime_presentation_for(command, message):
    """Resolve one resident-runtime failure from the same declarative registry."""
    if not isinstance(message, str) or not message:
        return RUNTIME_FALLBACK_KEY, ()
    for rule in REGISTRY:
        if not _runtime_scope_matches(rule, command):
            continue
        shape = rule["match"]
        if shape == "literal":
            if message == rule["message"]:
                return rule["key"], ()
            continue
        if shape == "prefix":
            # Resident detail is stripped before resolution. Generic raised
            # messages keep the registry's authored trailing space, but the
            # runtime boundary cannot: compare the same identity without
            # requiring whitespace that normalization has already removed.
            prefix = rule["prefix"].rstrip()
            if not message.startswith(prefix):
                continue
            remainder = message[len(prefix):].strip()
            arguments = (remainder,) if rule.get("argument") == "remainder" else ()
            return rule["key"], arguments
        if shape == "regex":
            match = re.match(rule["pattern"], message)
            if match is None:
                continue
            arguments = tuple(group or "" for group in match.groups())
            if rule.get("argument") == "absent":
                arguments = ()
            return rule["key"], arguments
    return RUNTIME_FALLBACK_KEY, ()

def presentation_for(message, diagnostic: Optional[str] = None):
    """Return `(key, arguments)` for a raised message, or `(None, [])`.

    `None` means the message is not registered Hades player-facing copy, so the
    caller keeps its own value untouched.
    """
    if not isinstance(message, str) or not message:
        return None, []
    key = _LITERALS.get(message)
    if key is not None:
        return key, []
    for _index, pattern, rule in _COMPILED:
        match = pattern.match(message)
        if match is None:
            continue
        # Group order is the template's {n} order, so the static wording stays
        # in the module's own table instead of riding along as an argument.
        # Positions are preserved: dropping a group would shift every later
        # value into the wrong placeholder. An absent optional value is kept as
        # an empty string so its position still holds.
        arguments = [group or '' for group in match.groups()]
        # A regex rule declares `argument` like every other rule. Honouring it
        # is what stops a rule from claiming one convention and being dispatched
        # under another: with this check, changing a rule's argument to
        # "absent" changes behaviour instead of being silently ignored.
        if rule.get("argument") == "absent":
            return rule["key"], []
        return rule["key"], arguments
    for rule in REGISTRY:
        if rule.get("runtime_only"):
            continue
        shape = rule["match"]
        if shape == "prefix":
            prefix = rule["prefix"]
            if not message.startswith(prefix):
                continue
            remainder = message[len(prefix):]
            # A composed message is kept whole as one argument: splitting it
            # further would bake structure into a localized sentence.
            return rule["key"], [remainder] if rule.get("argument") == "remainder" else []
        if shape == "affix":
            lead, tail = rule["prefix"], rule["suffix"]
            if not message.startswith(lead) or not message.endswith(tail):
                continue
            value = message[len(lead):len(message) - len(tail)].strip()
            if not value:
                continue
            return rule["key"], [value]
        if shape == "segmented":
            lead = rule["prefix"]
            if not message.startswith(lead):
                continue
            middle, tail = rule["separator"], rule["terminator"]
            rest = message[len(lead):]
            split = rest.find(middle)
            if split < 0:
                continue
            value, remainder = rest[:split].strip(), rest[split + len(middle):]
            split2 = remainder.find(tail)
            if split2 < 0:
                continue
            code, detail = remainder[:split2], remainder[split2 + len(tail):]
            if not value or not code:
                continue
            return rule["key"], [value, code, detail]
        if shape == "delimited":
            opening, closing = rule["open"], rule["close"]
            start = message.find(opening)
            if start < 0:
                continue
            begin = start + len(opening)
            end = message.find(closing, begin)
            if end <= begin:
                continue
            return rule["key"], [message[begin:end]]
    return None, []
