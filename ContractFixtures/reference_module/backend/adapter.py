import json
from core.adapter import AdapterError, GameAdapter
from core.persistence import ProfileStore, utc_iso_timestamp

_PROFILE_SCHEMA_VERSION = 1


def _invalid_name(*_args):
    return AdapterError('profile_invalid', 'referenceFixture.error.profileInvalid')


def _newer_format(*_args):
    return AdapterError('profile_unsupported_schema', 'referenceFixture.error.profileNewerFormat')


def _read_failed(_reason=None, error=None):
    diagnostic = str(error) if error is not None else None
    return AdapterError('profile_read_failed', 'referenceFixture.error.profileReadFailed', diagnostic=diagnostic)


def _write_failed(error):
    return AdapterError('profile_write_failed', 'referenceFixture.error.profileWriteFailed', diagnostic=str(error))


def _normalize_profile_features(payload, _version):
    if not isinstance(payload, dict):
        raise ValueError('Profile payload must be an object')
    enabled = payload.get('enabled', False)
    if type(enabled) is not bool:
        raise ValueError('Profile enabled flag must be a boolean')
    return {'enabled': enabled}


class ReferenceFixtureAdapter(GameAdapter):
    def __init__(self, context):
        super().__init__(context)
        self.connected = False
        self.enabled = False
        self.profiles = ProfileStore(
            context.data_dir / 'profiles',
            schema_version=_PROFILE_SCHEMA_VERSION,
            compatibility_floor=1,
            payload_key='features',
            normalize_payload=_normalize_profile_features,
            prepare_save_payload=lambda payload: _normalize_profile_features(payload, _PROFILE_SCHEMA_VERSION),
            game_id=context.game_id,
            slug_length=None,
            serialize=lambda document: json.dumps(document, ensure_ascii=False, allow_nan=False),
            timestamp=utc_iso_timestamp,
            quarantine_corrupt=False,
            create_root_dir=False,
            include_shortcuts_in_list=True,
            invalid_name_error=_invalid_name,
            corrupt_error=_read_failed,
            not_found_error=lambda _name: AdapterError('profile_not_found', 'referenceFixture.error.profileNotFound'),
            delete_not_found_error=lambda _name: AdapterError('profile_not_found', 'referenceFixture.error.profileNotFound'),
            newer_schema_error=_newer_format,
            older_schema_error=lambda _found, _supported: _read_failed('older_schema'),
            invalid_payload_input_error=lambda _reason: AdapterError(
                'invalid_value', 'referenceFixture.error.invalidValue'
            ),
            list_error=lambda error: _read_failed('list_failed', error),
            write_error=_write_failed,
        )

    def _state_payload(self):
        return {'connected': self.connected, 'enabled': self.enabled}

    def dispatch(self, command, params, request_id):
        if command == 'status':
            return self._state_payload()
        if command == 'connect':
            self.connected = True
            return self._state_payload()
        if command == 'disconnect':
            self.connected = False
            return self._state_payload()
        if command == 'set_enabled':
            self.enabled = bool(params.get('value', False))
            return self._state_payload()
        if command == 'disable_all':
            self.enabled = False
            return self._state_payload()
        if command == 'list_profiles':
            return {'profiles': self.profiles.list()}
        if command == 'save_profile':
            profiles = self.profiles.save(
                params.get('name'),
                {'enabled': self.enabled},
                params.get('shortcuts'),
            )
            return {'profiles': profiles}
        if command == 'load_profile':
            record = self.profiles.load(params.get('name'))
            self.enabled = bool(record['features'].get('enabled', False))
            return {
                **self._state_payload(),
                'shortcuts': record['shortcuts'],
                'profiles': self.profiles.list(),
            }
        if command == 'delete_profile':
            _name, profiles = self.profiles.delete(params.get('name'))
            return {'profiles': profiles}
        if command == 'diagnostics':
            saved_count = len(self.profiles.list())
            return {
                **self._state_payload(),
                'diagnostics': {
                    'checks': [
                        {
                            'id': 'backend_session',
                            'name': 'referenceFixture.diagnostics.session.name',
                            'ok': True,
                            'detail': 'referenceFixture.diagnostics.session.detail',
                            'detailArguments': [self.context.display_name],
                        },
                        {
                            'id': 'profile_store',
                            'name': 'referenceFixture.diagnostics.profileStore.name',
                            'ok': True,
                            'detail': 'referenceFixture.diagnostics.profileStore.detail',
                            'detailArguments': [str(saved_count)],
                        },
                    ],
                    'state': self._state_payload(),
                },
            }
        if command == 'fail':
            # Exercises the host envelope end to end: a stable presentation
            # key, its arguments, and technical detail that stays diagnostic.
            raise AdapterError(
                'reference_failure',
                'referenceFixture.error.failed',
                diagnostic='reference fixture diagnostic detail',
                arguments=['Fixture Game', '42'],
            )
        raise ValueError('unknown reference-fixture command')

    def close(self):
        self.connected = False
