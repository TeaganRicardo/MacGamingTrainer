from collections import OrderedDict
import json
import logging

# Host protocol covers only the JSONL envelope and request semantics. Each game
# module has its own independent protocol/schema version exposed alongside it.
HOST_PROTOCOL_VERSION = 5
PROTOCOL_VERSION = HOST_PROTOCOL_VERSION  # compatibility alias for older module code
APP_BACKEND_VERSION = '0.1'


from core.adapter import GameAdapter


class JsonlRequestRouter:
    def __init__(self, adapter: GameAdapter):
        self.adapter = adapter
        self.cache = OrderedDict()

    def _envelope(self, request_id, ok):
        return {
            'id': request_id,
            'type': 'result',
            'ok': ok,
            'protocolVersion': HOST_PROTOCOL_VERSION,
            'gameID': self.adapter.game_id,
            'moduleProtocolVersion': self.adapter.module_protocol_version,
        }

    def error_reply(self, request_id, code, message, state=None):
        reply = self._envelope(request_id, False)
        reply['error'] = {'code': code, 'message': message}
        if isinstance(state, dict):
            candidate = dict(state)
            if self._json_safe(candidate):
                reply['state'] = candidate
        return reply

    @staticmethod
    def _json_safe(value):
        try:
            json.dumps(value, ensure_ascii=False, allow_nan=False)
            return True
        except (TypeError, ValueError):
            return False

    @classmethod
    def _require_json_safe(cls, value, message):
        if not cls._json_safe(value):
            raise TypeError(message)

    def handle(self, request):
        request_id = request.get('id') if isinstance(request, dict) else None
        if not isinstance(request_id, str) or not request_id or len(request_id) > 128:
            return self.error_reply(None, 'invalid_request', '请求 ID 无效。')
        try:
            fingerprint = json.dumps(request, sort_keys=True, ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError):
            return self.error_reply(request_id, 'invalid_request', '请求包含不可序列化的 JSON 值。')
        if request_id in self.cache:
            old, reply = self.cache[request_id]
            return reply if old == fingerprint else self.error_reply(request_id, 'duplicate_conflict', '同一请求 ID 的内容发生变化。')
        try:
            command = request.get('command')
            params = request.get('params', {})
            if not isinstance(command, str) or not command or len(command) > 128:
                raise ValueError('command 无效。')
            if not isinstance(params, dict):
                raise ValueError('params 必须是对象。')
            if command == 'hello':
                result = {
                    'backendVersion': APP_BACKEND_VERSION,
                    'hostProtocolVersion': HOST_PROTOCOL_VERSION,
                    'game': self.adapter.metadata(),
                }
            else:
                result = self.adapter.dispatch(command, params, request_id)
                if not isinstance(result, dict):
                    raise TypeError('Game adapter dispatch() must return a JSON object.')
            self._require_json_safe(result, 'Game adapter returned a non-JSON-safe result.')
            reply = self._envelope(request_id, True)
            reply['result'] = result
            logging.info('request %s %s success game=%s', request_id, command, self.adapter.game_id)
        except Exception as error:
            logging.exception('request %s failed game=%s', request_id, self.adapter.game_id)
            state = getattr(self.adapter, 'state', None)
            code = getattr(error, 'code', 'invalid_request' if isinstance(error, ValueError) else 'operation_failed')
            reply = self.error_reply(request_id, code, str(error), state)
        self.cache[request_id] = (fingerprint, reply)
        while len(self.cache) > 256:
            self.cache.popitem(last=False)
        return reply

    def close(self):
        self.adapter.close()
