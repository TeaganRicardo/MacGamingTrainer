from core.adapter import GameAdapter


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
        raise ValueError('unknown reference-fixture command')

    def close(self):
        self.connected = False
