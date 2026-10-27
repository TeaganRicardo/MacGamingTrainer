"""Hades-owned feature presets. Native saves and one-shot actions stay separate."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile

from core.adapter import AdapterError
from .schema import preference_document


class HadesProfileStore:
    def __init__(self, root):
        self.root = Path(root)

    @staticmethod
    def name(value):
        if not isinstance(value, str):
            raise AdapterError('profile_invalid', 'hades.error.profileInvalid')
        value = value.strip()
        if not 1 <= len(value) <= 64 or any(ord(ch) < 32 for ch in value) or '/' in value or '\\' in value:
            raise AdapterError('profile_invalid', 'hades.error.profileInvalid')
        return value

    def path(self, name):
        return self.root / (hashlib.sha256(self.name(name).encode('utf-8')).hexdigest() + '.json')

    def _read(self, path):
        try:
            value = json.loads(path.read_text(encoding='utf-8'))
            if (not isinstance(value, dict) or set(value) != {'schemaVersion', 'gameID', 'name', 'updatedAt', 'features'}
                    or type(value['schemaVersion']) is not int or value['schemaVersion'] != 1 or value['gameID'] != 'hades'
                    or self.path(value['name']) != path or self.name(value['name']) != value['name']
                    or not isinstance(value['updatedAt'], str) or not value['updatedAt']):
                raise ValueError('Invalid Hades profile envelope')
            value['features'] = preference_document(value['features'])
            return value
        except (OSError, ValueError, AdapterError) as error:
            raise AdapterError('profile_read_failed', 'hades.error.profileReadFailed', diagnostic=str(error)) from error

    def list(self):
        try:
            paths = sorted(self.root.glob('*.json'))
            rows = [self._read(path) for path in paths]
            return sorted(({'name': row['name'], 'updatedAt': row['updatedAt']} for row in rows),
                          key=lambda row: row['name'].casefold())
        except OSError as error:
            raise AdapterError('profile_read_failed', 'hades.error.profileReadFailed', diagnostic=str(error)) from error

    def load(self, name):
        return self._read(self.path(name))['features']

    def save(self, name, features):
        name = self.name(name)
        document = {'schemaVersion': 1, 'gameID': 'hades', 'name': name,
                    'updatedAt': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                    'features': preference_document(features)}
        temporary = None
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            descriptor, temporary_name = tempfile.mkstemp(prefix='.profile-', dir=self.root)
            temporary = Path(temporary_name)
            with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
                json.dump(document, stream, ensure_ascii=False, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path(name))
        except OSError as error:
            raise AdapterError('profile_write_failed', 'hades.error.profileWriteFailed', diagnostic=str(error)) from error
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def delete(self, name):
        try:
            self.path(name).unlink()
        except OSError as error:
            raise AdapterError('profile_write_failed', 'hades.error.profileWriteFailed', diagnostic=str(error)) from error
