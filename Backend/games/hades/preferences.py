import json
import os
from pathlib import Path
import tempfile

from core.adapter import AdapterError
from .schema import DEFAULT_FEATURES, feature_document


class HadesPreferenceStore:
    def __init__(self, path=None):
        self.path = Path(path) if path is not None else (
            Path.home() / 'Library/Application Support/MacGamingTrainer/hades/preferences.json')

    def load(self):
        try:
            document = json.loads(self.path.read_text())
        except FileNotFoundError:
            return dict(DEFAULT_FEATURES)
        except (OSError, ValueError) as error:
            raise AdapterError('preferences_failed', 'hades.error.preferencesFailed', diagnostic=str(error)) from error
        if not isinstance(document, dict) or document.get('schemaVersion') != 1:
            raise AdapterError('preferences_failed', 'hades.error.preferencesFailed')
        try:
            return feature_document(document.get('features'))
        except AdapterError as error:
            raise AdapterError('preferences_failed', 'hades.error.preferencesFailed') from error

    def save(self, features):
        document = {'schemaVersion': 1, 'features': feature_document(features)}
        temporary = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, name = tempfile.mkstemp(prefix='.preferences-', dir=self.path.parent)
            temporary = Path(name)
            with os.fdopen(fd, 'w') as stream:
                json.dump(document, stream, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        except OSError as error:
            raise AdapterError('preferences_failed', 'hades.error.preferencesFailed', diagnostic=str(error)) from error
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
