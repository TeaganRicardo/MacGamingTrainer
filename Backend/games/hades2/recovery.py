"""Durable receipts for one game-process lifetime; never a replay queue."""
import json

from core.adapter import AdapterError
from core.runtime_recovery import (
    ProcessLifetime, RecoveryDocument, RuntimeRecoveryJournal, identified_start,
)
from core.runtime_recovery import RecoveryRequest as RecoveryRequest
from core.runtime_recovery import process_identity as identify_process
from core.target_probe import bounded_run
from .operation_budgets import PROCESS_QUERY_TIMEOUT_SECONDS


def process_identity(pid):
    return identify_process(pid, PROCESS_QUERY_TIMEOUT_SECONDS, run=bounded_run)


class _ReceiptCodec:
    exclusive = False

    def decode(self, document):
        if (
            not isinstance(document, dict)
            or set(document) != {'schemaVersion', 'pid', 'identity', 'requests'}
            or type(document['schemaVersion']) is not int or document['schemaVersion'] != 1
            or type(document['pid']) is not int or document['pid'] <= 0
            or document['identity'] is not None and not isinstance(document['identity'], str)
            or not isinstance(document['requests'], list) or not document['requests']
        ):
            raise ValueError('Invalid or unsupported runtime recovery document')
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
                raise ValueError('Invalid runtime recovery receipt')
            identifiers.add(request['id'])
        return RecoveryDocument(ProcessLifetime(document['pid'], document['identity']), document['requests'])

    @staticmethod
    def to_document(document):
        return {
            'schemaVersion': 1, 'pid': document.lifetime.pid, 'identity': document.lifetime.identity,
            'requests': document.requests,
        }

    def encode(self, document):
        return json.dumps(self.to_document(document), sort_keys=True) + '\n'


def _recovery_error(reason, detail=None):
    if reason == 'storage':
        return AdapterError('recovery_failed', 'hades2.error.recoveryFailed', diagnostic=str(detail) if detail else None)
    if reason == 'unknown':
        return AdapterError('outcome_unknown', 'hades2.error.outcomeUnknownGeneric')
    key = 'commandResultConnectionLost' if reason == 'confirmed' else 'restartRequired'
    return AdapterError('restart_required', 'hades2.error.' + key)


class Hades2RecoveryJournal:
    def __init__(self, path, identity=process_identity):
        self._journal = RuntimeRecoveryJournal(path, _ReceiptCodec(), _recovery_error)
        self.path = self._journal.path
        self.identity_provider = identity
        self.lifetime = None
        self.ready = False
        self.superseded = False

    def read(self):
        document = self._journal.read()
        return _ReceiptCodec.to_document(document) if document is not None else None

    def bind(self, pid):
        identity = identified_start(self.identity_provider(pid))
        self._journal.prepare(ProcessLifetime(pid, identity), allow_confirmed=True)
        self.lifetime = (pid, identity)
        self.ready = False
        self.superseded = False

    def _allows_confirmed(self, method):
        return method == 'status' or self.ready

    def guard(self, pid, method):
        if self.superseded or type(pid) is not int or pid <= 0:
            raise AdapterError('disconnected', 'hades2.error.notConnected')
        if self.lifetime is None:
            self.bind(pid)
        if self.lifetime[0] != pid:
            raise AdapterError('restart_required', 'hades2.error.restartRequired')
        self._journal.guard(ProcessLifetime(*self.lifetime), allow_confirmed=self._allows_confirmed(method))

    def begin(self, pid, method, request_id=None):
        self.guard(pid, method)
        return self._journal.begin(
            ProcessLifetime(*self.lifetime), method, request_id, allow_confirmed=self._allows_confirmed(method),
        )

    def require_current(self, request, pid):
        if request is not None and (
            pid != request.pid or self.lifetime is None
            or not self._journal.current(request, ProcessLifetime(*self.lifetime))
        ):
            self.superseded = True
            raise AdapterError('disconnected', 'hades2.error.notConnected')

    def confirm(self, request, receipt=None):
        self._journal.finish(request, outcome='confirmed', receipt=receipt)

    def unknown(self, request, receipt=None):
        self._journal.finish(request, outcome='unknown', receipt=receipt)

    def complete(self, request):
        self._journal.finish(request)

    def runtime_ready(self):
        self._journal.retire_confirmed(ProcessLifetime(*self.lifetime))
        self.ready = True

    def describe(self):
        return self._journal.describe()
