"""Durable receipts for one game-process lifetime; never a replay queue."""
from dataclasses import dataclass
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import uuid

from core.adapter import AdapterError
from core.persistence import atomic_write_text, fsync_directory
from core.target_probe import bounded_run
from .operation_budgets import PROCESS_QUERY_TIMEOUT_SECONDS


_PROCESS_IDENTITY_PREFIX = 'ps-utc-v1:'


def _identified_start(value):
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value or not value.isprintable():
        return None
    if value.startswith(_PROCESS_IDENTITY_PREFIX):
        start = value[len(_PROCESS_IDENTITY_PREFIX):].strip()
        return _PROCESS_IDENTITY_PREFIX + ' '.join(start.split()) if start else None
    # Earlier ps identities used local wall time without recording its zone.
    # Their whitespace-delimited timestamps cannot prove same-PID replacement.
    # Opaque identity-provider tokens remain comparable.
    return value if not any(character.isspace() for character in value) else None


def process_identity(pid):
    try:
        result = bounded_run(
            ['/bin/ps', '-p', str(pid), '-o', 'lstart='],
            PROCESS_QUERY_TIMEOUT_SECONDS,
            text=True,
            check=False,
            env={**os.environ, 'TZ': 'UTC', 'LC_ALL': 'C'},
        )
    except OSError:
        return None
    if result.returncode != 0 or not isinstance(result.stdout, str) or not result.stdout.strip():
        return None
    return _identified_start(_PROCESS_IDENTITY_PREFIX + result.stdout.strip())


@dataclass(frozen=True)
class RecoveryRequest:
    pid: int
    identity: object
    identifier: str


class Hades2RecoveryJournal:
    def __init__(self, path, identity=process_identity):
        self.path = Path(path)
        self.identity_provider = identity
        self.lifetime = None
        self.ready = False
        self.superseded = False

    @contextmanager
    def _locked(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.with_suffix(self.path.suffix + '.lock').open('a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(lock, fcntl.LOCK_UN)
        except OSError as error:
            raise self._failure(error) from error

    @staticmethod
    def _failure(error=None):
        return AdapterError('recovery_failed', 'hades2.error.recoveryFailed', diagnostic=str(error) if error else None)

    def read(self):
        try:
            document = json.loads(self.path.read_text())
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as error:
            raise self._failure(error) from error
        if (
            not isinstance(document, dict)
            or set(document) != {'schemaVersion', 'pid', 'identity', 'requests'}
            or type(document['schemaVersion']) is not int or document['schemaVersion'] != 1
            or type(document['pid']) is not int or document['pid'] <= 0
            or document['identity'] is not None and not isinstance(document['identity'], str)
            or not isinstance(document['requests'], list) or not document['requests']
        ):
            raise self._failure('Invalid or unsupported runtime recovery document')
        identifiers = set()
        for request in document['requests']:
            if (
                not isinstance(request, dict)
                or set(request) != {'id', 'method', 'requestId', 'outcome', 'receipt'}
                or not isinstance(request['id'], str) or not request['id'] or request['id'] in identifiers
                or not isinstance(request['method'], str) or not request['method']
                or request['requestId'] is not None and not isinstance(request['requestId'], str)
                or request['outcome'] not in ('unknown', 'confirmed')
                or request['receipt'] is not None and not isinstance(request['receipt'], dict)
            ):
                raise self._failure('Invalid runtime recovery receipt')
            identifiers.add(request['id'])
        return document

    def _write(self, document):
        try:
            if document is None or not document['requests']:
                self.path.unlink(missing_ok=True)
                fsync_directory(self.path.parent)
            else:
                atomic_write_text(self.path, json.dumps(document, sort_keys=True) + '\n')
        except OSError as error:
            raise self._failure(error) from error

    @staticmethod
    def _different(document, pid, identity):
        current = _identified_start(identity)
        previous = _identified_start(document['identity'])
        return (type(pid) is int and pid > 0 and current is not None
                and (document['pid'] != pid or previous is not None and previous != current))

    @staticmethod
    def _same(document, pid, identity):
        current = _identified_start(identity)
        return (current is not None and document['pid'] == pid
                and _identified_start(document['identity']) == current)

    def bind(self, pid):
        identity = _identified_start(self.identity_provider(pid))
        with self._locked():
            document = self.read()
            if document is not None:
                if self._different(document, pid, identity):
                    # Only fresh process identification at the attachment seam
                    # can retire a prior lifetime. Late requests cannot do it.
                    self._write(None)
                elif not self._same(document, pid, identity):
                    raise AdapterError('restart_required', 'hades2.error.restartRequired')
                elif any(row['outcome'] == 'unknown' for row in document['requests']):
                    raise AdapterError('outcome_unknown', 'hades2.error.outcomeUnknownGeneric')
        self.lifetime = (pid, identity)
        self.ready = False
        self.superseded = False

    def guard(self, pid, method):
        if self.superseded:
            raise AdapterError('disconnected', 'hades2.error.notConnected')
        if type(pid) is not int or pid <= 0:
            raise AdapterError('disconnected', 'hades2.error.notConnected')
        if self.lifetime is None:
            self.bind(pid)
        if self.lifetime[0] != pid:
            raise AdapterError('restart_required', 'hades2.error.restartRequired')
        self._guard_document(self.read(), method)

    def _guard_document(self, document, method):
        if document is None:
            return
        if not self._same(document, *self.lifetime):
            raise AdapterError('restart_required', 'hades2.error.restartRequired')
        if any(row['outcome'] == 'unknown' for row in document['requests']):
            raise AdapterError('outcome_unknown', 'hades2.error.outcomeUnknownGeneric')
        if method != 'status' and not self.ready:
            raise AdapterError('restart_required', 'hades2.error.commandResultConnectionLost')

    def begin(self, pid, method, request_id=None):
        self.guard(pid, method)
        with self._locked():
            document = self.read()
            self._guard_document(document, method)
            document = document or {
                'schemaVersion': 1, 'pid': self.lifetime[0], 'identity': self.lifetime[1], 'requests': [],
            }
            identifier = uuid.uuid4().hex
            document['requests'].append({
                'id': identifier, 'method': method,
                'requestId': request_id if isinstance(request_id, str) else None,
                'outcome': 'unknown', 'receipt': None,
            })
            self._write(document)
        return RecoveryRequest(*self.lifetime, identifier)

    def require_current(self, request, pid):
        if request is not None:
            document = self.read()
            if ((request.pid, request.identity) != self.lifetime or pid != request.pid
                    or document is None
                    or (document['pid'], document['identity']) != (request.pid, request.identity)
                    or not any(row['id'] == request.identifier for row in document['requests'])):
                self.superseded = True
                raise AdapterError('disconnected', 'hades2.error.notConnected')

    def _change(self, request, change):
        with self._locked():
            document = self.read()
            if document is None or (document['pid'], document['identity']) != (request.pid, request.identity):
                return
            for row in document['requests']:
                if row['id'] == request.identifier:
                    change(document, row)
                    self._write(document)
                    return

    def confirm(self, request, receipt=None):
        if request is not None:
            self._change(request, lambda document, row: row.update(outcome='confirmed', receipt=receipt))

    def unknown(self, request, receipt=None):
        if request is not None:
            self._change(request, lambda document, row: row.update(outcome='unknown', receipt=receipt))

    def complete(self, request):
        if request is not None:
            self._change(request, lambda document, row: document['requests'].remove(row))

    def runtime_ready(self):
        with self._locked():
            document = self.read()
            if document is not None:
                if not self._same(document, *self.lifetime):
                    raise AdapterError('restart_required', 'hades2.error.restartRequired')
                if any(row['outcome'] == 'unknown' for row in document['requests']):
                    raise AdapterError('outcome_unknown', 'hades2.error.outcomeUnknownGeneric')
                self._write(None)
        self.ready = True

    def describe(self):
        document = self.read()
        if document is None:
            return None
        request = next((row for row in document['requests'] if row['outcome'] == 'unknown'), document['requests'][-1])
        result = {key: request[key] for key in ('method', 'requestId', 'outcome', 'receipt')}
        result['pid'] = document['pid']
        return result
