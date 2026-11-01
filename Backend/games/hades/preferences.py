import json
from pathlib import Path

from core.adapter import AdapterError
from core.persistence import atomic_write_text
from .schema import DEFAULT_PREFERENCES, preference_document


class HadesPreferenceStore:
    def __init__(self, path=None):
        self.path = Path(path) if path is not None else (
            Path.home() / 'Library/Application Support/MacGamingTrainer/hades/preferences.json')

    def load(self):
        try:
            document = json.loads(self.path.read_text())
        except FileNotFoundError:
            return dict(DEFAULT_PREFERENCES)
        except (OSError, ValueError) as error:
            raise AdapterError('preferences_failed', 'hades.error.preferencesFailed', diagnostic=str(error)) from error
        if not isinstance(document, dict) or document.get('schemaVersion') != 1:
            raise AdapterError('preferences_failed', 'hades.error.preferencesFailed')
        features = document.get('features')
        # Schema 1 has three shipped feature sets, extended only by neutral
        # durable settings. An unknown or partially corrupted set stays invalid.
        if isinstance(features, dict):
            original = {'invincibility', 'moneyNoDecrease', 'rerollsNoDecrease',
                        'fullGodGauge', 'damageMultiplier', 'moveSpeedMultiplier',
                        'attackSpeedMultiplier', 'dashBonus'}
            shipped = (original, original | {'boonRarityEnabled'},
                       original | {'boonRarityEnabled', 'gameSpeed'})
            if set(features) in shipped:
                features = {**DEFAULT_PREFERENCES, **features}
        try:
            return preference_document(features)
        except AdapterError as error:
            raise AdapterError('preferences_failed', 'hades.error.preferencesFailed') from error

    def save(self, features):
        document = {'schemaVersion': 1, 'features': preference_document(features)}
        try:
            atomic_write_text(self.path, json.dumps(document, allow_nan=False))
        except OSError as error:
            raise AdapterError('preferences_failed', 'hades.error.preferencesFailed', diagnostic=str(error)) from error
