"""User-facing Hades II runtime error presentation.

The resident runtime and transport keep technical error detail for diagnostics.
This module translates known player-action failures at the Hades boundary so
Core can remain game-agnostic and the UI never depends on Lua source locations.

Following the B03 split, the raised presentation value is a language-neutral key
resolved by the module's shipped bilingual tables; the readable text stays on the
diagnostic so the operator trace is unchanged.
"""
import logging
import re

from core.adapter import AdapterError

from .error_presentation import Hades2PresentationError, presentation_for

_LUA_SOURCE_PREFIX = re.compile(r'^\[string "[^"]*"\]:\d+:\s*')

# Lua runtime detail -> presentation key. The message is Lua source text, so it
# is the stable identity here rather than a localized string.
_RUNTIME_KEYS = {
    'open_sell_traits': {
        'Cannot open boon sell screen while another screen is active':
            'hades2.error.sellScreenBusy',
        'Boon selling requires an active run room':
            'hades2.error.sellNeedsRunRoom',
        'Native boon sell screen data is unavailable':
            'hades2.error.sellDataUnavailable',
    },
    'remove_trait': {
        'Trait removal requires an active run room':
            'hades2.error.traitRemovalNeedsRun',
        'Trait removal requires a trait name':
            'hades2.error.traitRemovalNeedsName',
        'Native sell predicate is unavailable':
            'hades2.error.sellPredicateUnavailable',
        'Trait is not sell-eligible, so no safe removal exists':
            'hades2.error.traitNotSellEligible',
        'Trait is not present in the current run':
            'hades2.error.traitNotPresent',
    },
    'open_special_choice': {
        'Cannot open special blessing choice while another screen is active':
            'hades2.error.choiceScreenBusy',
        'Cannot open special blessing choice during a transition':
            'hades2.error.choiceDuringTransition',
        'Special blessing choice requires an active run room':
            'hades2.error.choiceNeedsRunRoom',
        'Special blessing source has no audited native choice flow':
            'hades2.error.choiceNoAuditedFlow',
        'Special blessing source data is unavailable':
            'hades2.error.choiceSourceUnavailable',
        'Special blessing choice data is unavailable':
            'hades2.error.choiceDataUnavailable',
        'No eligible special blessings are available':
            'hades2.error.noEligibleSpecialRewards',
    },
}

_FALLBACK_KEY = 'hades2.error.runtimeActionFailed'

# Per-command composed messages: the stable leading text selects the key and the
# remainder is a runtime value (a trait name), never copy.
_COMPOSED_PREFIXES = {
    'remove_trait': (
        ('Trait is not sell-eligible, so no safe removal exists:',
         'hades2.error.traitNotSellEligible'),
        ('Trait removal is not proven safe:', 'hades2.error.traitRemovalNotProven'),
        ('Trait is not present in the current run:', 'hades2.error.traitNotPresent'),
    ),
}


def present_runtime_error(command, error):
    if not isinstance(error, AdapterError) or error.code != 'lua_error':
        return error

    raw = str(error)
    detail = _LUA_SOURCE_PREFIX.sub('', raw).strip()
    command_keys = _RUNTIME_KEYS.get(command, {})
    diagnostic = error.diagnostic if isinstance(error.diagnostic, str) and error.diagnostic else raw

    key = command_keys.get(detail)
    arguments = ()
    if key is None and _COMPOSED_PREFIXES.get(command):
        # A command-scoped refusal may append a runtime value, e.g. a trait
        # name. The whole message is this command's own text, so resolve it
        # through the same mapper the raised path uses: that splits the value
        # out as an argument instead of dropping it, and avoids falling back to
        # a generic "operation failed" that tells the player nothing.
        for prefix, expected in _COMPOSED_PREFIXES[command]:
            if detail.startswith(prefix):
                key = expected
                arguments = (detail[len(prefix):].strip(),)
                break
    if key is None:
        key = _FALLBACK_KEY
    logging.warning('Hades Lua error command=%s raw=%s', command, raw)
    return Hades2PresentationError(error.code, key, arguments, diagnostic=diagnostic)
