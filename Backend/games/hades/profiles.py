"""Hades-owned preset storage over the shared Core ProfileStore."""
import json
from pathlib import Path

from core.adapter import AdapterError
from core.persistence import ProfileStore, utc_iso_timestamp
from .schema import (
    PREFERENCE_SCHEMA_VERSION,
    persisted_preference_document,
    preference_document,
)


def _invalid_name(*_args):
    return AdapterError('profile_invalid', 'hades.error.profileInvalid')


def _newer_format(*_args):
    return AdapterError('profile_unsupported_schema', 'hades.error.profileNewerFormat')


def _read_failed(_reason=None, error=None):
    diagnostic = str(error) if error is not None else None
    return AdapterError('profile_read_failed', 'hades.error.profileReadFailed', diagnostic=diagnostic)


def _write_failed(error):
    return AdapterError('profile_write_failed', 'hades.error.profileWriteFailed', diagnostic=str(error))


class HadesProfileStore:
    def __init__(self, root):
        self.root = Path(root)
        self._store = ProfileStore(
            self.root,
            schema_version=PREFERENCE_SCHEMA_VERSION,
            compatibility_floor=1,
            payload_key='features',
            normalize_payload=lambda features, version: persisted_preference_document(version, features),
            prepare_save_payload=preference_document,
            game_id='hades',
            slug_length=None,
            serialize=lambda document: json.dumps(document, ensure_ascii=False, allow_nan=False),
            timestamp=utc_iso_timestamp,
            quarantine_corrupt=False,
            create_root_dir=False,
            include_shortcuts_in_list=False,
            invalid_name_error=_invalid_name,
            corrupt_error=_read_failed,
            not_found_error=lambda _name: _read_failed('not_found'),
            newer_schema_error=_newer_format,
            older_schema_error=lambda _found, _supported: _read_failed('older_schema'),
            invalid_payload_input_error=lambda _reason: AdapterError('invalid_value', 'hades.error.invalidValue'),
            list_error=lambda error: _read_failed('list_failed', error),
            write_error=_write_failed,
        )

    @staticmethod
    def name(value):
        return ProfileStore.sanitize_profile_name(value, _invalid_name)

    def path(self, name):
        return self._store.path(name)

    def list(self):
        return self._store.list()

    def load_record(self, name):
        return self._store.load(name)

    def load(self, name):
        return self._store.load(name)['features']

    def save(self, name, features, shortcuts=None):
        self._store.save(name, features, shortcuts)

    def delete(self, name):
        self._store.delete(name)
