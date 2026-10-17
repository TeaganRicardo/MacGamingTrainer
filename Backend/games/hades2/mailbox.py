"""Hades command publication and receipts over the native single-flight mailbox.

Only the game-thread consumer evaluates Lua.  This process owns byte publication,
bounded waiting and the distinction between a cancelled request and unknown work.
The native implementation is also loaded locally so C11 atomics, rather than
Python mmap writes, publish every cross-process transition.
"""
import ctypes
import logging
import math
import mmap
import os
from pathlib import Path
import secrets
import tempfile
import time

from core.adapter import AdapterError
from core.operation_profile import record
from .config import LUA_TRANSPORT_RESULT_LIMIT_BYTES, LUA_TRANSPORT_SOURCE_LIMIT_BYTES


OK, EMPTY, BUSY, STALE, INVALID, CLOSED, POISONED, DUPLICATE, CAPACITY = range(9)
SUCCESS, ERROR, CANCELLED, UNKNOWN = range(4)
# Rejection before source evaluation, emitted by the verified native consumer.
GENERATION_CHANGED = -1000


class _Receipt(ctypes.Structure):
    _fields_ = [
        ("generation_hi", ctypes.c_uint64),
        ("generation_lo", ctypes.c_uint64),
        ("sequence", ctypes.c_uint64),
        ("outcome", ctypes.c_uint32),
        ("status", ctypes.c_int32),
        ("length", ctypes.c_size_t),
        ("execution_ns", ctypes.c_uint64),
        ("queue_ns", ctypes.c_uint64),
    ]


def _bind_library(path):
    library = ctypes.CDLL(str(path))
    pointer, u64 = ctypes.c_void_p, ctypes.c_uint64
    u32, size = ctypes.c_uint32, ctypes.c_size_t
    signatures = {
        "MGTMailboxABI": ([], u32),
        "MGTMailboxSize": ([], size),
        "MGTMailboxInit": ([pointer, size, u64, u64, u32, u32], ctypes.c_int),
        "MGTMailboxSubmit": ([pointer, u64, u64, u64, pointer, size], ctypes.c_int),
        "MGTMailboxRead": ([pointer, u64, u64, u64, ctypes.POINTER(_Receipt), pointer, size], ctypes.c_int),
        "MGTMailboxAck": ([pointer, u64, u64, u64], ctypes.c_int),
        "MGTMailboxCancel": ([pointer, u64, u64, u64], ctypes.c_int),
        "MGTMailboxClose": ([pointer, u64, u64], ctypes.c_int),
        "MGTMailboxPoison": ([pointer, u64, u64], ctypes.c_int),
        "MGTMailboxDiagnostics": ([pointer, u64, u64, ctypes.POINTER(u64), size], ctypes.c_int),
    }
    for name, (arguments, result) in signatures.items():
        function = getattr(library, name)
        function.argtypes, function.restype = arguments, result
    if library.MGTMailboxABI() != 2:
        raise ValueError("Incompatible Hades command mailbox ABI")
    return library


class Hades2CommandMailbox:
    """One attachment lease; a closed or poisoned lease is never reopened."""

    def __init__(self, library_path, target_pid, *, alive, clock=time.monotonic, wait=time.sleep):
        self.library_path = Path(library_path)
        self.library = _bind_library(self.library_path)
        self.target_pid = target_pid
        self._alive, self._clock, self._wait = alive, clock, wait
        self._sequence = 0
        self._pending_sequence = None
        self._closed = False
        self.tainted = False
        self.installed = False
        self.last_profile = {}
        self._mapping = None
        self._buffer = None
        self._temporary = tempfile.TemporaryDirectory(prefix="mgt-hades2-mailbox-")
        self.path = Path(self._temporary.name) / "commands"
        self.generation_hi, self.generation_lo = secrets.randbits(64), secrets.randbits(64)
        if not (self.generation_hi or self.generation_lo):
            self.generation_lo = 1
        try:
            length = self.library.MGTMailboxSize()
            if not LUA_TRANSPORT_SOURCE_LIMIT_BYTES + LUA_TRANSPORT_RESULT_LIMIT_BYTES <= length < 2_000_000:
                raise ValueError("Invalid Hades command mailbox mapping size")
            descriptor = os.open(self.path, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            try:
                os.ftruncate(descriptor, length)
                self._mapping = mmap.mmap(descriptor, length, flags=mmap.MAP_SHARED,
                                          prot=mmap.PROT_READ | mmap.PROT_WRITE)
            finally:
                os.close(descriptor)
            self._buffer = ctypes.c_char.from_buffer(self._mapping)
            self.address = ctypes.c_void_p(ctypes.addressof(self._buffer))
            result = self.library.MGTMailboxInit(
                self.address, length, self.generation_hi, self.generation_lo,
                os.getpid(), target_pid,
            )
            if result != OK:
                raise ValueError("Cannot initialize Hades command mailbox: " + str(result))
        except BaseException:
            self._release()
            raise

    def installed_in_target(self):
        # Both processes now own independent mappings. No named stale mailbox
        # survives a crash, and no frame callback performs filesystem I/O.
        self.path.unlink()
        self.installed = True

    def _call(self, name, *arguments):
        return getattr(self.library, name)(
            self.address, self.generation_hi, self.generation_lo, *arguments,
        )

    def poison(self):
        self.tainted = True
        if self._mapping is not None:
            self._call("MGTMailboxPoison")

    def diagnostics(self):
        """A bounded atomic snapshot; it neither evaluates Lua nor drives a frame."""
        if self._mapping is None:
            return {}
        values = (ctypes.c_uint64 * 6)()
        result = self._call("MGTMailboxDiagnostics", values, len(values))
        if result != OK:
            raise ValueError("Cannot inspect Hades command mailbox: " + str(result))
        return dict(zip(("state", "flags", "heartbeatCount", "heartbeatNanoseconds",
                         "claimedCount", "completedCount"), values))

    def _unknown(self, detail):
        self.poison()
        return AdapterError("outcome_unknown", "hades2.error.outcomeUnknownGeneric", diagnostic=detail)

    def _read(self, sequence, output):
        receipt = _Receipt()
        result = self._call("MGTMailboxRead", sequence, ctypes.byref(receipt), output, len(output))
        if result in (EMPTY, BUSY):
            return None
        if result != OK:
            raise self._unknown("Mailbox receipt could not be read: " + str(result))
        if (receipt.generation_hi, receipt.generation_lo, receipt.sequence) != (
            self.generation_hi, self.generation_lo, sequence
        ) or receipt.length > LUA_TRANSPORT_RESULT_LIMIT_BYTES:
            raise self._unknown("Mailbox receipt identity or size is invalid")
        if receipt.outcome not in (SUCCESS, ERROR, CANCELLED, UNKNOWN):
            raise self._unknown("Mailbox receipt outcome is invalid")
        if ((receipt.outcome == SUCCESS and receipt.status != 0)
                or (receipt.outcome == ERROR and receipt.status == 0)
                or (receipt.outcome == CANCELLED
                    and (receipt.status != 0 or receipt.length != 0
                         or receipt.execution_ns != 0 or receipt.queue_ns != 0))):
            raise self._unknown("Mailbox receipt contains contradictory completion evidence")
        try:
            text = output.raw[:receipt.length].decode("utf-8", errors="strict")
        except UnicodeDecodeError as error:
            raise self._unknown("Mailbox returned invalid UTF-8") from error
        if receipt.outcome == UNKNOWN:
            raise self._unknown(text or "Native command completion is unknown")
        return receipt, text

    def acknowledge(self):
        """Called only after the resident owner has accepted the decoded result.

        A worker dying while its reply is in flight leaves an unacknowledged
        terminal slot in the game. Reconnecting cannot erase that uncertainty.
        """
        if self._pending_sequence is None:
            return
        if self._call("MGTMailboxAck", self._pending_sequence) != OK:
            raise self._unknown("Mailbox could not acknowledge the complete receipt")
        self._pending_sequence = None

    def _finish(self, sequence, read, started, payload_size):
        receipt, text = read
        duration = self._clock() - started
        execution = receipt.execution_ns / 1_000_000_000
        queue = receipt.queue_ns / 1_000_000_000
        self.last_profile = {
            "sequence": sequence, "roundTripSeconds": duration,
            "queueSeconds": queue, "executionSeconds": execution,
            "overheadSeconds": max(0.0, duration - queue - execution),
        }
        record("mailbox.round_trip", duration, request_bytes=payload_size, reply_bytes=receipt.length)
        record("mailbox.queue", queue)
        record("mailbox.execution", execution)
        logging.info("MailboxBoundary request=%d duration=%.6fs queue=%.6fs execution=%.6fs outcome=%d status=%d",
                     sequence, duration, queue, execution, receipt.outcome, receipt.status)
        self._pending_sequence = sequence
        if receipt.outcome == CANCELLED:
            self.acknowledge()
            raise AdapterError("waiting", "hades2.error.commandNotExecuted")
        if receipt.outcome == ERROR:
            if "MGT_OUTCOME_UNKNOWN:" in text:
                raise self._unknown(text)
            self.acknowledge()
            if receipt.status == GENERATION_CHANGED:
                raise AdapterError("resident_generation_missing", "Lua runtime generation changed before command execution")
            raise AdapterError("lua_error", text or "hades2.error.luaFailed")
        return text

    def execute(self, source, *, timeout_seconds=2.0):
        if self.tainted:
            raise AdapterError("restart_required", "hades2.error.restartRequired")
        if self._closed or not self.installed:
            raise AdapterError("disconnected", "hades2.error.notAttached")
        if self._pending_sequence is not None:
            raise AdapterError("mailbox_unacknowledged", "hades2.error.commandConnectionUnavailable",
                               diagnostic="The previous resident reply has not been accepted")
        if not isinstance(source, str):
            raise ValueError("Mailbox source must be text")
        payload = source.encode("utf-8")
        if not 0 < len(payload) <= LUA_TRANSPORT_SOURCE_LIMIT_BYTES:
            raise AdapterError("invalid_request", "hades2.error.featureCodeTooLong")
        if type(timeout_seconds) not in (int, float) or not math.isfinite(timeout_seconds) or not 0 < timeout_seconds <= 30:
            raise ValueError("Mailbox timeout must be within (0, 30].")
        if not self._alive():
            raise AdapterError("disconnected", "hades2.error.notAttached")
        self._sequence += 1
        if self._sequence >= 2 ** 64:
            raise AdapterError("restart_required", "hades2.error.restartRequired")
        sequence = self._sequence
        output = ctypes.create_string_buffer(LUA_TRANSPORT_RESULT_LIMIT_BYTES)
        started = self._clock()
        published = False
        finished = False
        self.last_profile = {}
        try:
            result = self._call("MGTMailboxSubmit", sequence, ctypes.c_char_p(payload), len(payload))
            if result != OK:
                if result == POISONED:
                    raise self._unknown("Native mailbox lease is poisoned")
                raise AdapterError("mailbox_unavailable", "hades2.error.commandConnectionUnavailable",
                                   diagnostic="Mailbox rejected publication: " + str(result))
            published = True
            deadline = started + timeout_seconds
            next_liveness_check = started
            while True:
                read = self._read(sequence, output)
                if read is not None:
                    finished = True
                    return self._finish(sequence, read, started, len(payload))
                now = self._clock()
                target_lost = False
                if now >= next_liveness_check:
                    target_lost = not self._alive()
                    next_liveness_check = now + 0.05
                if target_lost or now >= deadline:
                    if self._call("MGTMailboxCancel", sequence) == OK:
                        # The CAS beat the consumer's claim: execution is known
                        # not to have begun. Read and ack that cancellation.
                        cancelled = self._read(sequence, output)
                        if cancelled is None or cancelled[0].outcome != CANCELLED:
                            raise self._unknown("Mailbox cancellation has no matching receipt")
                        finished = True
                        self._pending_sequence = sequence
                        self.acknowledge()
                        raise AdapterError("disconnected" if target_lost else "waiting",
                                           "hades2.error.commandNotExecuted")
                    # A completion may have raced the deadline. A complete,
                    # validated receipt still resolves it without a retry.
                    read = self._read(sequence, output)
                    if read is not None:
                        finished = True
                        return self._finish(sequence, read, started, len(payload))
                    raise self._unknown("Game exited during the command" if target_lost
                                        else "Mailbox execution exceeded its completion deadline")
                self._wait(min(0.001, max(0.0, deadline - now)))
        except BaseException:
            if published and not finished and not self.tainted:
                try:
                    if self._call("MGTMailboxCancel", sequence) == OK:
                        cancelled = self._read(sequence, output)
                        if cancelled is None or cancelled[0].outcome != CANCELLED:
                            self.poison()
                        else:
                            self._pending_sequence = sequence
                            self.acknowledge()
                    else:
                        self.poison()
                except BaseException:
                    # Preserve the caller's interruption, while preventing an
                    # incomplete cleanup from making the lease reusable.
                    self.poison()
            raise

    def _release(self):
        self._buffer = None
        if self._mapping is not None:
            self._mapping.close()
            self._mapping = None
        self._temporary.cleanup()

    def close(self):
        if self._closed:
            return
        self._closed = True
        if self._mapping is not None:
            self._call("MGTMailboxClose")
        self._release()
