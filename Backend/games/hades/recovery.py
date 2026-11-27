import json

from core.adapter import AdapterError
from core.runtime_recovery import ProcessLifetime, RecoveryDocument, RuntimeRecoveryJournal
from core.runtime_recovery import process_identity as identify_process
from core.target_probe import bounded_run
from .operation_budgets import PROCESS_IDENTITY_TIMEOUT_SECONDS

RECOVERY_SCHEMA_VERSION = 2


def process_identity(pid):
    return identify_process(pid, PROCESS_IDENTITY_TIMEOUT_SECONDS, run=bounded_run)


class _SingleRequestCodec:
    exclusive = True

    def decode(self, pending):
        if not isinstance(pending, dict):
            raise ValueError('Invalid runtime recovery document')
        if 'schemaVersion' in pending:
            version = pending.get('schemaVersion')
            if type(version) is not int or version != RECOVERY_SCHEMA_VERSION:
                raise ValueError('Unsupported runtime recovery document schemaVersion')
            if set(pending) != {'schemaVersion', 'pid', 'identity', 'method', 'outcome', 'receipt'}:
                raise ValueError('Invalid runtime recovery document')
            pid = pending['pid']
            identity = pending['identity']
            method = pending['method']
            outcome = pending['outcome']
            receipt = pending['receipt']
            if (type(pid) is not int or pid <= 0
                    or (identity is not None and not isinstance(identity, str))
                    or not isinstance(method, str) or not method
                    or outcome not in ('unknown', 'confirmed')
                    or (receipt is not None and not isinstance(receipt, dict))):
                raise ValueError('Invalid runtime recovery document')
            return RecoveryDocument(ProcessLifetime(pid, identity), [{
                'id': method, 'method': method,
                'requestId': receipt.get('requestId') if isinstance(receipt, dict) else None,
                'outcome': outcome, 'receipt': receipt,
            }])
        if set(pending) != {'pid', 'identity', 'method'}:
            raise ValueError('Invalid runtime recovery document')
        return RecoveryDocument(ProcessLifetime(pending['pid'], pending['identity']), [{
            'id': pending['method'], 'method': pending['method'],
            'requestId': None, 'outcome': 'unknown', 'receipt': None,
        }])

    def encode(self, document):
        row = document.requests[0]
        outcome = row.get('outcome', 'unknown')
        receipt = row.get('receipt')
        if outcome == 'unknown' and receipt is None:
            return json.dumps({
                'pid': document.lifetime.pid, 'identity': document.lifetime.identity,
                'method': row['method'],
            })
        return json.dumps({
            'schemaVersion': RECOVERY_SCHEMA_VERSION,
            'pid': document.lifetime.pid,
            'identity': document.lifetime.identity,
            'method': row['method'],
            'outcome': outcome,
            'receipt': receipt,
        }, sort_keys=True)


def _recovery_error(reason, detail=None):
    if reason == 'storage':
        return AdapterError('recovery_failed', 'hades.error.recoveryFailed', diagnostic=str(detail) if detail else None)
    if reason == 'confirmed':
        return AdapterError('restart_required', 'hades.error.commandResultConnectionLost')
    return AdapterError('restart_required', 'hades.error.restartRequired')


class HadesRecoveryJournal:
    def __init__(self, path):
        self._journal = RuntimeRecoveryJournal(path, _SingleRequestCodec(), _recovery_error)
        self.path = self._journal.path

    def guard(self, pid, identity):
        self._journal.prepare(ProcessLifetime(pid, identity))

    def begin(self, pid, identity, method):
        return self._journal.begin(ProcessLifetime(pid, identity), method)

    def confirm(self, pending, receipt=None):
        self._journal.finish(pending, outcome='confirmed', receipt=receipt)

    def current(self, pending, pid, identity):
        if pending is None:
            return True
        return self._journal.current(pending, ProcessLifetime(pid, identity))

    def require_current(self, pending, pid, identity):
        if pending is not None and not self.current(pending, pid, identity):
            raise AdapterError('debugger_lost', 'hades.error.debuggerLost')

    def complete(self, pending):
        self._journal.finish(pending)

    def describe(self):
        return self._journal.describe()
