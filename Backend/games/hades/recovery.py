import json

from core.adapter import AdapterError
from core.runtime_recovery import ProcessLifetime, RecoveryDocument, RuntimeRecoveryJournal
from core.runtime_recovery import process_identity as identify_process
from core.target_probe import bounded_run
from .operation_budgets import PROCESS_IDENTITY_TIMEOUT_SECONDS


def process_identity(pid):
    return identify_process(pid, PROCESS_IDENTITY_TIMEOUT_SECONDS, run=bounded_run)


class _SingleRequestCodec:
    exclusive = True

    def decode(self, pending):
        if not isinstance(pending, dict) or set(pending) != {'pid', 'identity', 'method'}:
            raise ValueError('Invalid runtime recovery document')
        return RecoveryDocument(ProcessLifetime(pending['pid'], pending['identity']), [{
            'id': pending['method'], 'method': pending['method'],
            'requestId': None, 'outcome': 'unknown', 'receipt': None,
        }])

    def encode(self, document):
        return json.dumps({
            'pid': document.lifetime.pid, 'identity': document.lifetime.identity,
            'method': document.requests[0]['method'],
        })


def _recovery_error(reason, detail=None):
    if reason == 'storage':
        return AdapterError('recovery_failed', 'hades.error.recoveryFailed', diagnostic=str(detail) if detail else None)
    return AdapterError('restart_required', 'hades.error.restartRequired')


class HadesRecoveryJournal:
    def __init__(self, path):
        self._journal = RuntimeRecoveryJournal(path, _SingleRequestCodec(), _recovery_error)
        self.path = self._journal.path

    def guard(self, pid, identity):
        self._journal.prepare(ProcessLifetime(pid, identity))

    def begin(self, pid, identity, method):
        return self._journal.begin(ProcessLifetime(pid, identity), method)

    def complete(self, pending):
        self._journal.finish(pending)
