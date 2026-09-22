from collections import OrderedDict
from pathlib import Path
import json
import logging
import plistlib
import subprocess

# Host protocol covers only the JSONL envelope and request semantics. Each game
# module has its own independent protocol/schema version exposed alongside it.
HOST_PROTOCOL_VERSION = 5
PROTOCOL_VERSION = HOST_PROTOCOL_VERSION  # compatibility alias for older module code


def _product_version():
    """Read the app-level SemVer without introducing a second version source.

    Source-tree execution finds the repository Info.plist. A packaged backend
    finds Contents/Info.plist. Detached test fixtures may have neither; in that
    case 0.0.0 is an explicit non-release sentinel, not a product version.
    """
    source = Path(__file__).resolve()
    for parent_index in (2, 3):
        candidate = source.parents[parent_index] / 'Info.plist'
        if not candidate.is_file():
            continue
        try:
            with candidate.open('rb') as stream:
                value = plistlib.load(stream).get('CFBundleShortVersionString')
        except (OSError, ValueError, plistlib.InvalidFileException):
            continue
        if isinstance(value, str):
            parts = value.split('.')
            if len(parts) == 3 and all(part.isdigit() for part in parts):
                return value
    return '0.0.0'


APP_BACKEND_VERSION = _product_version()


from core.adapter import GameAdapter
from core.save_service import CoreSaveService
from core.save_restore import SaveBusyError


_CORE_SAVE_PREFIX = 'core.save.'


def _target_process_running(process_name):
    if not process_name:
        return False
    try:
        result = subprocess.run(
            ['/usr/bin/pgrep', '-x', process_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise SaveBusyError('无法确认目标游戏是否正在运行，请稍后重试。') from error
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    raise SaveBusyError('无法确认目标游戏是否正在运行，请稍后重试。')


class JsonlRequestRouter:
    def __init__(self, adapter: GameAdapter, save_data_root=None, target_running_probe=None):
        self.adapter = adapter
        self.cache = OrderedDict()
        context = adapter.context
        self.save_service = CoreSaveService(
            adapter.game_id,
            getattr(context, 'save_management', None),
            Path(save_data_root) if save_data_root is not None else Path.home() / 'Library/Application Support/MacGamingTrainer',
            target_running_probe or (lambda: _target_process_running(getattr(context, 'process_name', ''))),
        )

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

    @staticmethod
    def _require_empty(params):
        if params:
            raise ValueError('该 Core 存档命令不接受参数。')

    @staticmethod
    def _snapshot_id(params):
        snapshot_id = params.get('snapshotId')
        if not isinstance(snapshot_id, str) or not snapshot_id:
            raise ValueError('snapshotId 无效。')
        return snapshot_id

    def _with_state(self, operation):
        return {'operation': operation, **self.save_service.list_state()}

    def _dispatch_core_save(self, command, params):
        if command == 'core.save.list':
            self._require_empty(params)
            return self.save_service.list_state()
        if command == 'core.save.backup':
            name = params.get('name')
            if name is not None and not isinstance(name, str):
                raise ValueError('name 无效。')
            return self._with_state(self.save_service.backup(display_name=name))
        if command == 'core.save.rename':
            snapshot_id = self._snapshot_id(params)
            name = params.get('name')
            if not isinstance(name, str):
                raise ValueError('name 无效。')
            return self._with_state(self.save_service.rename(snapshot_id, name))
        if command == 'core.save.delete':
            return self._with_state(self.save_service.delete(self._snapshot_id(params)))
        if command == 'core.save.open_folder':
            snapshot_id = params.get('snapshotId')
            if snapshot_id is not None and (not isinstance(snapshot_id, str) or not snapshot_id):
                raise ValueError('snapshotId 无效。')
            return {'folder': self.save_service.folder(snapshot_id), **self.save_service.list_state()}
        if command == 'core.save.restore':
            snapshot_id = self._snapshot_id(params)
            preserve_current = params.get('preserveCurrent', True)
            if type(preserve_current) is not bool:
                raise ValueError('preserveCurrent 必须为布尔值。')
            return self._with_state(self.save_service.restore(snapshot_id, preserve_current=preserve_current))
        if command == 'core.save.cancel_staged':
            self._require_empty(params)
            return self._with_state(self.save_service.cancel_staged())
        if command == 'core.save.apply_staged':
            self._require_empty(params)
            return self._with_state(self.save_service.apply_staged())
        raise ValueError('未知 Core 存档命令。')

    def handle(self, request):
        request_id = request.get('id') if isinstance(request, dict) else None
        if not isinstance(request_id, str) or not request_id or len(request_id) > 128:
            return self.error_reply(None, 'invalid_request', '请求 ID 无效。')
        try:
            fingerprint = json.dumps(request, sort_keys=True, ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError):
            return self.error_reply(request_id, 'invalid_request', '请求包含不可序列化的 JSON 值。')
        if request_id in self.cache:
            old, reply_json = self.cache[request_id]
            return json.loads(reply_json) if old == fingerprint else self.error_reply(request_id, 'duplicate_conflict', '同一请求 ID 的内容发生变化。')
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
            elif command.startswith(_CORE_SAVE_PREFIX):
                result = self._dispatch_core_save(command, params)
            else:
                result = self.adapter.dispatch(command, params, request_id)
                if not isinstance(result, dict):
                    raise TypeError('Game adapter dispatch() must return a JSON object.')
            self._require_json_safe(result, 'Backend returned a non-JSON-safe result.')
            reply = self._envelope(request_id, True)
            reply['result'] = result
            logging.info('request %s %s success game=%s', request_id, command, self.adapter.game_id)
        except Exception as error:
            logging.exception('request %s failed game=%s', request_id, self.adapter.game_id)
            state = getattr(self.adapter, 'state', None)
            code = getattr(error, 'code', 'invalid_request' if isinstance(error, ValueError) else 'operation_failed')
            reply = self.error_reply(request_id, code, str(error), state)
            recovery_path = getattr(error, 'recovery_path', None)
            if code == 'rollback_failed' and isinstance(recovery_path, str) and recovery_path:
                reply['error']['recoveryPath'] = recovery_path
        reply_json = json.dumps(reply, ensure_ascii=False, allow_nan=False)
        self.cache[request_id] = (fingerprint, reply_json)
        while len(self.cache) > 256:
            self.cache.popitem(last=False)
        return json.loads(reply_json)

    def close(self):
        self.adapter.close()
