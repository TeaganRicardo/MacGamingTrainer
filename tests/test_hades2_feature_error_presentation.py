"""Resident feature failures reach the frontend as registry presentations.

featureAttempt stores the raw `tostring(message)` of a failed install. That text
stays available for diagnostics, but the public state must carry a presentation
token for every failed feature; the frontend otherwise used the raw runtime text
itself as a localization key and showed it untranslated in both languages.
"""
import logging
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))
sys.path.insert(0, str(ROOT / 'tests'))
logging.disable(logging.WARNING)

from games.hades2 import preparation  # noqa: E402
from games.hades2.adapter import Hades2Adapter  # noqa: E402
from hades2_resident_session_fakes import FakeResidentSession, FakeTimeWarpController  # noqa: E402

MISSING_NATIVE = '[string "MGTHades2Runtime"]:812: Unsupported infinite ammo: missing SetAmmo'
UNKNOWN_FAILURE = '[string "MGTHades2Runtime"]:901: attempt to index a nil value'
PAYLOAD = {
    'status': 'ready', 'scene': 'run', 'capabilities': {'setFeature': True},
    'desiredFeatures': {'infiniteAmmo': True, 'instantCastCooldown': True},
    'activeFeatures': {}, 'dormantFeatures': {}, 'stats': {}, 'resources': [], 'elements': [],
    'featureErrors': {'infiniteAmmo': MISSING_NATIVE, 'instantCastCooldown': UNKNOWN_FAILURE},
}

with tempfile.TemporaryDirectory(prefix='hades2-feature-errors-') as directory:
    preparation.DATA = Path(directory)
    adapter = Hades2Adapter(resident_session=FakeResidentSession(payload=PAYLOAD),
                            time_warp_controller=FakeTimeWarpController())
    adapter.preference_initialized = True
    state = adapter.execute('status', {})
    presentations = state['featureErrorPresentations']
    assert presentations['infiniteAmmo'] == {
        'presentation': 'hades2.error.nativeFunctionMissing', 'arguments': ['infinite ammo', 'SetAmmo'],
    }, presentations
    assert presentations['instantCastCooldown'] == {
        'presentation': 'hades2.error.runtimeActionFailed', 'arguments': [],
    }, presentations
    # The raw runtime text remains the diagnostic, not the presentation.
    assert state['featureErrors']['infiniteAmmo'] == MISSING_NATIVE

print('hades2_feature_error_presentation_ok')
