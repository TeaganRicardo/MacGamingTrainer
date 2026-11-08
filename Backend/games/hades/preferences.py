import json
from pathlib import Path

from core.adapter import AdapterError
from core.persistence import atomic_write_text
from .schema import (DEFAULT_PREFERENCES, PREFERENCE_SCHEMA_VERSION, newer_preference_schema,
                     persisted_preference_document, preference_document)


def refuse_replacing_newer_schema(path, error):
    """Never replace a document a newer Trainer wrote; this version cannot interpret it.

    An absent or unreadable document is replaced as before.
    """
    try:
        document = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return
    if newer_preference_schema(document):
        raise error()


def _newer_format():
    return AdapterError('preferences_unsupported_schema', 'hades.error.preferencesNewerFormat')


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
            raise AdapterError('preferences_failed', 'hades.error.preferencesReadFailed', diagnostic=str(error)) from error
        if newer_preference_schema(document):
            raise _newer_format()
        if not isinstance(document, dict):
            raise AdapterError('preferences_failed', 'hades.error.preferencesReadFailed')
        try:
            return persisted_preference_document(document.get('schemaVersion'), document.get('features'))
        except AdapterError as error:
            raise AdapterError('preferences_failed', 'hades.error.preferencesReadFailed') from error

    def save(self, features):
        document = {'schemaVersion': PREFERENCE_SCHEMA_VERSION, 'features': preference_document(features)}
        refuse_replacing_newer_schema(self.path, _newer_format)
        try:
            atomic_write_text(self.path, json.dumps(document, allow_nan=False))
        except OSError as error:
            raise AdapterError('preferences_failed', 'hades.error.preferencesFailed', diagnostic=str(error)) from error
