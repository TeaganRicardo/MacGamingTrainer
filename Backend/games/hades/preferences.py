import json
from pathlib import Path

from core.adapter import AdapterError
from core.persistence import VersionedDocumentStore
from .schema import (
    DEFAULT_PREFERENCES,
    PREFERENCE_SCHEMA_VERSION,
    persisted_preference_document,
    preference_document,
)


def _newer_format(*_args):
    return AdapterError('preferences_unsupported_schema', 'hades.error.preferencesNewerFormat')


def _read_failed(_reason, error=None):
    if isinstance(error, AdapterError):
        return AdapterError('preferences_failed', 'hades.error.preferencesReadFailed', diagnostic=error.diagnostic)
    diagnostic = str(error) if error is not None else None
    return AdapterError('preferences_failed', 'hades.error.preferencesReadFailed', diagnostic=diagnostic)


def _write_failed(error):
    return AdapterError('preferences_failed', 'hades.error.preferencesFailed', diagnostic=str(error))


def _store_for(path):
    return VersionedDocumentStore(
        path,
        schema_version=PREFERENCE_SCHEMA_VERSION,
        compatibility_floor=1,
        defaults=lambda: dict(DEFAULT_PREFERENCES),
        normalize=lambda raw, version: persisted_preference_document(version, raw.get('features')),
        build_document=lambda features, version: {'schemaVersion': version, 'features': preference_document(features)},
        serialize=lambda document: json.dumps(document, allow_nan=False),
        quarantine_corrupt=False,
        fallback_on_error=False,
        newer_schema_error=_newer_format,
        older_schema_error=lambda _found, _supported: _read_failed('older_schema'),
        read_error=_read_failed,
        write_error=_write_failed,
    )


def refuse_replacing_newer_schema(path, error):
    """Never replace a document a newer Trainer wrote; this version cannot interpret it."""
    store = VersionedDocumentStore(
        path,
        schema_version=PREFERENCE_SCHEMA_VERSION,
        defaults=lambda: dict(DEFAULT_PREFERENCES),
        normalize=lambda raw, version: raw,
        newer_schema_error=lambda _found, _supported: error(),
    )
    store.protect_future_overwrite()


class HadesPreferenceStore:
    def __init__(self, path):
        self.path = Path(path)
        self._store = _store_for(self.path)

    def load(self):
        return self._store.load()

    def save(self, features):
        self._store.save(features)
