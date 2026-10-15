#!/usr/bin/env python3
"""Private offline worker: real owners, synthetic native functions/temp storage."""
from dataclasses import replace
import importlib.util
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import time

HARNESS = Path(__file__).resolve().parents[2]
SOURCE = Path(os.environ.get('MGT_PROFILE_SOURCE_ROOT', HARNESS))
sys.path[:0] = [str(SOURCE / 'Backend'), str(HARNESS / 'tests')]
# Older baseline sources predate probes. The external harness owns their
# wrappers; production-source identity and harness identity are recorded apart.
try:
    from core import operation_profile as profile
    PROBES = True
except ImportError:
    spec = importlib.util.spec_from_file_location('core.operation_profile', HARNESS / 'Backend/core/operation_profile.py')
    profile = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(profile)
    sys.modules['core.operation_profile'] = profile
    PROBES = False

logging.basicConfig(level=logging.INFO, format='%(message)s', filename=os.environ.get('MGT_PROFILE_EVENTS'))
for handler in logging.getLogger().handlers:
    handler.addFilter(lambda record: record.getMessage().startswith('OperationProfile '))
from core.sidecar import JsonLineSidecarClient
from games.hades2.resident_session import lua_value

class ProfileSidecar(JsonLineSidecarClient):
    def request(self, method, params=None, **kwargs):
        rpc_id = str(self._next_id)
        received = []
        original = self._readline
        def read(stream):
            raw = original(stream)
            received.append(len(raw.encode('utf-8')) if isinstance(raw, str) else len(raw))
            return raw
        self._readline = read
        started = time.perf_counter()
        try:
            result = super().request(method, params, **kwargs)
            if not PROBES:
                encoded = json.dumps({'id': rpc_id, 'method': method, 'params': params or {}},
                                     ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')
                profile.record('sidecar.rpc', time.perf_counter() - started, method=method,
                               request_bytes=len(encoded) + 1, reply_bytes=sum(received), count=1)
            # Join a baseline worker's per-RPC resident records to the Host id.
            identity = profile.correlation()
            if identity:
                logging.info('OperationProfile %s', json.dumps({**identity, 'schema': 1,
                    'component': 'harness', 'phase': 'sidecar.identity', 'seconds': 0,
                    'rpc_id': rpc_id}))
            return result
        finally:
            self._readline = original

class OfflineLuaTransport:
    def __init__(self):
        from lua_runtime_support import require_lua52
        self.pid, self.tainted, self.last_duration = 4242, False, 0.0
        self.last_expression_duration, self.last_attach_profile = 0.0, {}
        self.counter = 0
        self.events = open(os.environ["MGT_PROFILE_EVENTS"], "a", encoding="utf-8")
        self.lua = subprocess.Popen([
            require_lua52('operation profile'), str(HARNESS / 'Tools/fixtures/hades2_operation_profile.lua'),
            str(SOURCE / 'Backend/games/hades2/runtime/hades.lua'), '1',
            os.environ.get('MGT_PROFILE_TRAITS', '32'), os.environ.get('MGT_PROFILE_CATALOG', '96'),
            os.environ.get('MGT_PROFILE_RESOURCES', '32'), 'serve',
        ], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.events, text=True, bufsize=1)
    def alive(self):
        return self.pid is not None and self.lua.poll() is None
    def attach(self, pid):
        assert pid == 4242
    def detach(self):
        self.pid = None
    def close(self):
        self.pid = None
        self.lua.stdin.close()
        try:
            self.lua.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.lua.kill(); self.lua.wait(timeout=2)
        self.lua.stdout.close()
        self.events.close()
    def execute(self, source, **kwargs):
        identity = profile.correlation() or {'request_id': 'unobserved', 'command': 'fixture'}
        started = time.perf_counter()
        self.lua.stdin.write(identity['request_id'] + '\t' + identity['command'] + '\t' + lua_value(source) + '\n')
        self.lua.stdin.flush()
        result = self.lua.stdout.readline()
        if not result:
            raise RuntimeError('offline resident exited')
        self.last_duration = time.perf_counter() - started
        return result.strip()


def worker():
    from games.hades2.lldb_worker import Hades2LLDBWorker, serve_requests
    transport = OfflineLuaTransport()
    owner = Hades2LLDBWorker(transport=transport)
    original = owner.dispatch
    rpc_count = 0
    def dispatch(method, params):
        nonlocal rpc_count
        rpc_count += 1
        identity = profile.correlation() or {'request_id': 'rpc-' + str(rpc_count), 'command': method}
        with profile.operation(identity['request_id'], identity['command']):
            return original(method, params)
    owner.dispatch = dispatch
    try:
        serve_requests(sys.stdin, sys.stdout, owner)
    finally:
        transport.close()


def backend():
    from games.hades2 import preparation
    from games.hades2.adapter import Hades2Adapter
    from games.hades2.transport_client import Hades2LuaTransport, _LLDBWorkerClient
    from core.protocol import JsonlRequestRouter
    from core import server
    from hades2_resident_session_fakes import FakeTimeWarpController
    temporary = Path(os.environ['MGT_PROFILE_TEMP'])
    # The production localization owner also reads installed content by
    # default. Pin its input to a finite synthetic bilingual source tree.
    from games.hades2 import localization
    game = temporary / 'fixture-game.app'
    identifiers = {'MetaCurrency', 'Money', 'ZeusUpgrade', 'Boon', 'MetaCurrencyDrop'}
    identifiers.update('ProfileBoon%04d' % i for i in range(1, int(os.environ['MGT_PROFILE_CATALOG']) + 1))
    identifiers.update('ProfileResource%04d' % i for i in range(1, int(os.environ['MGT_PROFILE_RESOURCES'])))
    for language in ('en', 'zh-CN'):
        text = game / ('Contents/Resources/Content/Game/Text/' + language)
        text.mkdir(parents=True)
        (text / ('profile.' + language + '.sjson')).write_text('{ Texts = [\n' + '\n'.join(
            '{ Id = %s DisplayName = %s }' % (json.dumps(key), json.dumps('Synthetic ' + key))
            for key in sorted(identifiers)) + '\n] }\n', encoding='utf-8')
    localization.GAME_SPEC = replace(localization.GAME_SPEC, app_bundle_path=game,
        executable_path=game / 'Contents/MacOS/OfflineFixture', save_path=temporary / 'unused-saves')
    preparation.DATA = temporary / 'preferences'
    preparation.DATA.mkdir()
    transport = Hades2LuaTransport()
    sidecar = ProfileSidecar([sys.executable, '-u', str(Path(__file__).resolve()), '--sidecar'],
                            reply_timeout_seconds=15, env=dict(os.environ))
    transport._worker = _LLDBWorkerClient(sidecar=sidecar, on_state=transport._adopt_state)
    transport.attach(4242)
    adapter = Hades2Adapter(transport=transport, time_warp_controller=FakeTimeWarpController())
    adapter.state.update(pid=4242, connected=True)
    adapter.preference_initialized = True
    adapter.preference_dirty = False
    router = JsonlRequestRouter(adapter, save_data_root=temporary / 'saves', target_running_probe=lambda: False)
    try:
        for raw in sys.stdin:
            if PROBES:
                encoded = server.process_line(router, raw)
            else:
                started = time.perf_counter()
                request = json.loads(raw)
                decode = time.perf_counter() - started
                with profile.operation(request['id'], request['command']):
                    profile.record('backend.request_decode', decode, request_bytes=len(raw.encode('utf-8')))
                    with profile.phase('backend.routing'):
                        reply = router.handle(request)
                    started = time.perf_counter()
                    encoded = server.encode_reply(router, reply)
                    profile.record('backend.stdout_serialize', time.perf_counter() - started,
                                   reply_bytes=len(encoded.encode('utf-8')) + 1)
            print(encoded, flush=True)
    finally:
        transport.close()

if __name__ == '__main__':
    worker() if '--sidecar' in sys.argv else backend()
