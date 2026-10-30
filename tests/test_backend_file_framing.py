"""Large private worker messages retain bounded controls and session ownership."""
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))
from core.framing import JsonLineFileSession

WORKER = r'''
import sys
sys.path.insert(0, BACKEND_PATH)
from core.adapter import GameAdapter, GameAdapterContext
import core.server as server
class Fixture(GameAdapter):
    def __init__(self):
        super().__init__(GameAdapterContext('fixture', 'Fixture', 1, None, {}))
        self.calls = 0
    def dispatch(self, command, params, request_id):
        self.calls += 1
        return {'payload': params.get('payload'), 'calls': self.calls}
    def close(self):
        pass
server.available_games = lambda: []
server.create_adapter = lambda game_id: Fixture()
server.main()
'''


def make_session(directory):
    directory.mkdir(mode=0o700)
    (directory / 'session.json').write_text(json.dumps({'version': 1, 'inlineBytes': 65536, 'hostPID': os.getpid()}))
    return JsonLineFileSession(directory)


with tempfile.TemporaryDirectory(prefix='mgt-file-framing-') as temporary:
    root = Path(temporary)
    directory = root / 'session'
    session = make_session(directory)
    worker = root / 'worker.py'
    worker.write_text('BACKEND_PATH = ' + repr(str(ROOT / 'Backend')) + '\n' + WORKER)
    process = subprocess.Popen([sys.executable, '-u', str(worker), '--game', 'fixture'],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               env=dict(os.environ, MGT_JSONL_SESSION_V1=str(directory)))
    def exchange(request, *, framed=True):
        encoded = json.dumps(request, ensure_ascii=False)
        control = session.encode(encoded, request['id']) if framed else encoded
        assert len(control.encode('utf-8')) + 1 <= session.inline_bytes
        process.stdin.write(control.encode('utf-8') + b'\n')
        process.stdin.flush()
        assert select.select([process.stdout], [], [], 5)[0], 'worker did not reply'
        raw = process.stdout.readline(session.inline_bytes + 1)
        assert raw and len(raw) <= session.inline_bytes
        return session.decode(raw)

    # A legal string edit and its full reply exceed both historical limits;
    # control frames stay bounded, including escaped UTF-8 content.
    payload = '合法 complete\x00\n' * 100_000
    result = exchange({'id': 'large', 'command': 'echo', 'params': {'payload': payload}})
    assert result['ok'] and result['result'] == {'payload': payload, 'calls': 1}
    assert not list(directory.glob('payload-*.json'))

    outside = root / 'outside.json'
    outside.write_text('preserved outside bytes')
    invalid = exchange({'id': 'bad-path', 'type': 'mgt.file', 'file': '../outside.json', 'bytes': 100_000}, framed=False)
    assert invalid['id'] == 'bad-path' and invalid['ok'] is False
    assert outside.read_text() == 'preserved outside bytes'

    # Invalid file types/length/identity are rejected before dispatch, while
    # subsequent requests and the same worker's existing state remain usable.
    for kind in ('symlink', 'fifo', 'length', 'identity'):
        name = 'payload-' + uuid.uuid4().hex + '.json'
        path = directory / name
        if kind == 'symlink':
            path.symlink_to(outside)
            length = 100_000
        elif kind == 'fifo':
            os.mkfifo(path)
            length = 100_000
        elif kind == 'length':
            path.write_bytes(b'wrong-length')
            length = 100_000
        else:
            contents = json.dumps({'id': 'different', 'payload': 'x' * 100_000}).encode()
            path.write_bytes(contents)
            length = len(contents)
        rejected = exchange({'id': kind, 'type': 'mgt.file', 'file': name, 'bytes': length}, framed=False)
        assert rejected['id'] == kind and rejected['ok'] is False
        assert outside.read_text() == 'preserved outside bytes'
    followup = exchange({'id': 'after-errors', 'command': 'echo', 'params': {}})
    assert followup['ok'] and followup['result']['calls'] == 2
    metadata = exchange({'id': 'bad-command', 'command': 'x' * 129, 'params': {'payload': payload}})
    assert metadata['id'] == 'bad-command' and metadata['ok'] is False
    followup = exchange({'id': 'after-metadata', 'command': 'echo', 'params': {}})
    assert followup['ok'] and followup['result']['calls'] == 3

    other = make_session(root / 'other-session')
    descriptor = json.loads(other.encode(json.dumps({'id': 'old-session', 'payload': payload}), 'old-session'))
    isolated = exchange(descriptor, framed=False)
    assert isolated['id'] == 'old-session' and isolated['ok'] is False
    assert (other.directory / descriptor['file']).exists()
    other.close()

    # The producer's exact inline boundary is accepted by the consumer.
    boundary = json.dumps({'id': 'boundary', 'command': 'echo', 'params': {'payload': ''}})
    count = 65536 - len(boundary.encode())
    at_limit = {'id': 'boundary', 'command': 'echo', 'params': {'payload': 'x' * count}}
    assert len(json.dumps(at_limit).encode()) == 65536
    assert exchange(at_limit)['ok'] is True
    process.stdin.close()
    assert process.wait(timeout=5) == 0
    assert not list(directory.glob('payload-*.json'))
    session.close()

    # If the Host itself disappears, EOF reclaims only that worker's session.
    # os._exit keeps stdin open until the parent process actually exits.
    orphan_directory = root / 'orphan-session'
    orphan_worker = root / 'orphan.py'
    orphan_worker.write_text('BACKEND_PATH = ' + repr(str(ROOT / 'Backend')) + '\n' + WORKER +
                             '\nfrom pathlib import Path\nPath(__file__ + ".exited").touch()\n')
    launcher = root / 'host.py'
    launcher.write_text('''
import json, os, pathlib, subprocess, sys
directory = pathlib.Path(sys.argv[2])
directory.mkdir(mode=0o700)
(directory / 'session.json').write_text(json.dumps({'version': 1, 'inlineBytes': 65536, 'hostPID': os.getpid()}))
(directory / ('payload-' + 'a' * 32 + '.json')).write_text('unconsumed old payload')
worker = subprocess.Popen([sys.executable, '-u', sys.argv[1], '--game', 'fixture'],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    env=dict(os.environ, MGT_JSONL_SESSION_V1=str(directory)))
worker.stdin.write(b'{"id":"ready","command":"hello"}\\n')
worker.stdin.flush()
assert json.loads(worker.stdout.readline())['ok']
os._exit(0)
''')
    subprocess.run([sys.executable, str(launcher), str(orphan_worker), str(orphan_directory)], check=True, timeout=8)
    deadline = time.monotonic() + 5
    while not Path(str(orphan_worker) + '.exited').exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert Path(str(orphan_worker) + '.exited').exists(), 'orphan worker did not finish'
    assert not orphan_directory.exists(), 'orphan worker retained its private payloads'
    assert (other.directory / descriptor['file']).exists(), 'orphan cleanup crossed session ownership'

print('backend_file_framing_ok')
