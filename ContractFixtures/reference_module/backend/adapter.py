from core.adapter import AdapterError, GameAdapter


class ReferenceFixtureAdapter(GameAdapter):
    def __init__(self, context):
        super().__init__(context)
        self.connected = False
        self.enabled = False

    def dispatch(self, command, params, request_id):
        if command == 'status':
            return {'connected': self.connected, 'enabled': self.enabled}
        if command == 'connect':
            self.connected = True
            return {'connected': True, 'enabled': self.enabled}
        if command == 'disconnect':
            self.connected = False
            return {'connected': False, 'enabled': self.enabled}
        if command == 'set_enabled':
            self.enabled = bool(params.get('value', False))
            return {'connected': self.connected, 'enabled': self.enabled}
        if command == 'disable_all':
            self.enabled = False
            return {'connected': self.connected, 'enabled': False}
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
