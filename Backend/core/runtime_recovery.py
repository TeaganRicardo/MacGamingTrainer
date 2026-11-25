"""Durable request ownership and recovery policy for a process lifetime.

Callers supply their persisted format and errors, and decide which operations
may observe confirmed recovery. The journal owns lifetime comparison, outcome
admission, and locked compare/change transactions; it never dispatches work.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Callable, Iterator, Literal, Protocol
import uuid

from core.persistence import atomic_write_text, fsync_directory
from core.target_probe import bounded_run

_PROCESS_IDENTITY_PREFIX = 'ps-utc-v1:'
RecoveryFailure = Literal['storage', 'lifetime', 'unknown', 'confirmed']
RecoveryOutcome = Literal['unknown', 'confirmed']


def identified_start(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value or not value.isprintable():
        return None
    if value.startswith(_PROCESS_IDENTITY_PREFIX):
        start = value[len(_PROCESS_IDENTITY_PREFIX) :].strip()
        return _PROCESS_IDENTITY_PREFIX + ' '.join(start.split()) if start else None
    # Legacy wall-clock timestamps did not record their timezone. Opaque
    # provider tokens remain comparable, while those timestamps do not.
    return value if not any(character.isspace() for character in value) else None


def process_identity(pid: int, timeout: float, *, run: Callable[..., Any] = bounded_run) -> str | None:
    try:
        result = run(
            ['/bin/ps', '-p', str(pid), '-o', 'lstart='],
            timeout,
            text=True,
            check=False,
            env={**os.environ, 'TZ': 'UTC', 'LC_ALL': 'C'},
        )
    except OSError:
        return None
    if result.returncode != 0 or not isinstance(result.stdout, str) or not result.stdout.strip():
        return None
    return identified_start(_PROCESS_IDENTITY_PREFIX + result.stdout.strip())


@dataclass(frozen=True)
class ProcessLifetime:
    pid: int | None
    identity: object

    def replaces(self, previous: ProcessLifetime) -> bool:
        current_start = identified_start(self.identity)
        previous_start = identified_start(previous.identity)
        identified = (
            type(self.pid) is int
            and self.pid > 0
            and type(previous.pid) is int
            and previous.pid > 0
            and current_start is not None
        )
        return identified and (
            self.pid != previous.pid or previous_start is not None and previous_start != current_start
        )

    def same(self, previous: ProcessLifetime) -> bool:
        current_start = identified_start(self.identity)
        return (
            current_start is not None
            and self.pid == previous.pid
            and identified_start(previous.identity) == current_start
        )


@dataclass(frozen=True)
class RecoveryRequest:
    pid: int | None
    identity: object
    identifier: str

    @property
    def lifetime(self) -> ProcessLifetime:
        return ProcessLifetime(self.pid, self.identity)


@dataclass
class RecoveryDocument:
    lifetime: ProcessLifetime
    requests: list[dict[str, Any]]


class RecoveryCodec(Protocol):
    # A legacy single-request format has no durable request ID. Its method is
    # the record key and publication must refuse any existing destination.
    exclusive: bool

    def decode(self, value: Any) -> RecoveryDocument: ...

    def encode(self, document: RecoveryDocument) -> str: ...


class RuntimeRecoveryJournal:
    def __init__(
        self,
        path: Path | str,
        codec: RecoveryCodec,
        error: Callable[[RecoveryFailure, object], Exception],
    ) -> None:
        self.path = Path(path)
        self._codec = codec
        self._error = error

    @contextmanager
    def _locked(self) -> Iterator[None]:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # Replacing/unlinking the journal must never replace its lock inode.
            with self.path.with_name(self.path.name + '.lock').open('a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(lock, fcntl.LOCK_UN)
        except OSError as error:
            raise self._error('storage', error) from error

    def read(self) -> RecoveryDocument | None:
        try:
            return self._codec.decode(json.loads(self.path.read_text()))
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as error:
            raise self._error('storage', error) from error

    def _write(self, document: RecoveryDocument | None, *, exclusive: bool = False) -> None:
        if document is None or not document.requests:
            self.path.unlink(missing_ok=True)
            fsync_directory(self.path.parent)
        elif exclusive:
            temporary = None
            try:
                fd, name = tempfile.mkstemp(prefix='.runtime-request-', dir=self.path.parent)
                temporary = Path(name)
                with os.fdopen(fd, 'w') as stream:
                    stream.write(self._codec.encode(document))
                    stream.flush()
                    os.fsync(stream.fileno())
                os.link(temporary, self.path)
                fsync_directory(self.path.parent)
            except FileExistsError as error:
                raise self._error('unknown', None) from error
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
        else:
            atomic_write_text(self.path, self._codec.encode(document))

    def _guard(self, document: RecoveryDocument | None, lifetime: ProcessLifetime, allow_confirmed: bool) -> None:
        if document is None:
            return
        if not lifetime.same(document.lifetime):
            raise self._error('lifetime', None)
        if any(row['outcome'] == 'unknown' for row in document.requests):
            raise self._error('unknown', None)
        if not allow_confirmed:
            raise self._error('confirmed', None)

    def prepare(self, lifetime: ProcessLifetime, *, allow_confirmed: bool = False) -> None:
        """Only a fresh identification here may retire a previous lifetime."""
        with self._locked():
            document = self.read()
            if document is not None and lifetime.replaces(document.lifetime):
                self._write(None)
            else:
                self._guard(document, lifetime, allow_confirmed)

    def guard(self, lifetime: ProcessLifetime, *, allow_confirmed: bool = False) -> None:
        self._guard(self.read(), lifetime, allow_confirmed)

    def begin(
        self,
        lifetime: ProcessLifetime,
        method: str,
        request_id: str | None = None,
        *,
        allow_confirmed: bool = False,
    ) -> RecoveryRequest:
        with self._locked():
            document = None if self._codec.exclusive else self.read()
            self._guard(document, lifetime, allow_confirmed)
            document = document or RecoveryDocument(lifetime, [])
            identifier = method if self._codec.exclusive else uuid.uuid4().hex
            document.requests.append(
                {
                    'id': identifier,
                    'method': method,
                    'requestId': request_id if isinstance(request_id, str) else None,
                    'outcome': 'unknown',
                    'receipt': None,
                }
            )
            self._write(document, exclusive=self._codec.exclusive)
        return RecoveryRequest(lifetime.pid, lifetime.identity, identifier)

    @staticmethod
    def _owned(document: RecoveryDocument | None, request: RecoveryRequest) -> dict[str, Any] | None:
        if document is None or document.lifetime != request.lifetime:
            return None
        return next((row for row in document.requests if row['id'] == request.identifier), None)

    def current(self, request: RecoveryRequest, lifetime: ProcessLifetime) -> bool:
        return request.lifetime == lifetime and self._owned(self.read(), request) is not None

    def finish(
        self, request: RecoveryRequest | None, *, outcome: RecoveryOutcome | None = None, receipt: Any = None
    ) -> None:
        """Retire or update only the original request's durable record."""
        if request is None:
            return
        with self._locked():
            document = self.read()
            row = self._owned(document, request)
            if document is None or row is None:
                return
            if outcome is None:
                document.requests.remove(row)
            else:
                row.update(outcome=outcome, receipt=receipt)
            self._write(document)

    def retire_confirmed(self, lifetime: ProcessLifetime) -> None:
        with self._locked():
            document = self.read()
            self._guard(document, lifetime, allow_confirmed=True)
            if document is not None:
                self._write(None)

    def describe(self) -> dict[str, Any] | None:
        document = self.read()
        if document is None:
            return None
        request = next((row for row in document.requests if row['outcome'] == 'unknown'), document.requests[-1])
        result = {key: request[key] for key in ('method', 'requestId', 'outcome', 'receipt')}
        result['pid'] = document.lifetime.pid
        return result
