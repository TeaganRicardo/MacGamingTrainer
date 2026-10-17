"""Production Python/C producer ABI against a separately mapped native consumer."""
import ctypes
import multiprocessing
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from core.adapter import AdapterError
from games.hades2.mailbox import (
    BUSY, CANCELLED, CAPACITY, CLOSED, EMPTY, ERROR, GENERATION_CHANGED, OK,
    SUCCESS, Hades2CommandMailbox,
)


IDLE, POSTED, EXECUTING, COMPLETE = 0, 2, 3, 4
CLOSED_FLAG, POISONED_FLAG = 0x100, 0x200
RESULT_CAPACITY = 262144
SPAWN = multiprocessing.get_context("spawn")


class Request(ctypes.Structure):
    _fields_ = [
        ("sequence", ctypes.c_uint64),
        ("source", ctypes.c_void_p),
        ("length", ctypes.c_size_t),
    ]


class Snapshot(ctypes.Structure):
    _fields_ = [
        ("state", ctypes.c_uint32),
        ("flags", ctypes.c_uint32),
        ("highest_sequence", ctypes.c_uint64),
        ("claimed_count", ctypes.c_uint64),
        ("completed_count", ctypes.c_uint64),
    ]


def fixture_library(path):
    library = ctypes.CDLL(str(path), use_errno=True)
    pointer, u64, size = ctypes.c_void_p, ctypes.c_uint64, ctypes.c_size_t
    signatures = {
        "MGTTestMailboxMap": ([ctypes.c_char_p, u64, u64], pointer),
        "MGTTestMailboxUnmap": ([pointer], ctypes.c_int),
        "MGTTestMailboxClaim": ([pointer, ctypes.POINTER(Request)], ctypes.c_int),
        "MGTTestMailboxComplete": ([pointer, u64, ctypes.c_uint32, ctypes.c_int32,
                                    pointer, size, u64], ctypes.c_int),
        "MGTTestMailboxInspect": ([pointer, ctypes.POINTER(Snapshot)], None),
    }
    for name, (arguments, result) in signatures.items():
        function = getattr(library, name)
        function.argtypes, function.restype = arguments, result
    return library


def inspect(library, address):
    snapshot = Snapshot()
    library.MGTTestMailboxInspect(address, ctypes.byref(snapshot))
    return {name: getattr(snapshot, name) for name, _ in snapshot._fields_}


def receive(connection):
    if not connection.poll(5):
        raise AssertionError("Independent mailbox process did not reach its barrier")
    message = connection.recv()
    if message[0] == "error":
        raise AssertionError(message[1])
    return message


def consumer_process(connection, library_path):
    library = fixture_library(library_path)
    address = None
    request = None
    try:
        path, hi, lo = connection.recv()
        address = library.MGTTestMailboxMap(os.fsencode(path), hi, lo)
        if not address:
            raise OSError(ctypes.get_errno(), "Cannot independently map producer mailbox")
        connection.send(("mapped",))
        while True:
            operation, *arguments = connection.recv()
            if operation == "stop":
                break
            if operation == "inspect":
                connection.send(("snapshot", inspect(library, address)))
                continue
            if operation in ("roundtrip", "claim", "try_claim"):
                request = Request()
                deadline = time.monotonic() + 5
                while True:
                    result = library.MGTTestMailboxClaim(address, ctypes.byref(request))
                    if result == OK or operation == "try_claim" or result not in (EMPTY, BUSY):
                        break
                    if time.monotonic() >= deadline:
                        raise AssertionError("Consumer never observed a published request")
                    time.sleep(0.0001)
                if result != OK:
                    connection.send(("claim_result", result))
                    continue
                source = ctypes.string_at(request.source, request.length)
                if operation != "roundtrip":
                    connection.send(("claimed", request.sequence, source))
                    continue
            if operation in ("roundtrip", "complete"):
                if request is None:
                    raise AssertionError("Completion has no successful consumer claim")
                outcome, status, payload, *timing = arguments
                result = library.MGTTestMailboxComplete(
                    address, request.sequence, outcome, status,
                    ctypes.c_char_p(payload), len(payload), timing[0] if timing else 123_000,
                )
                connection.send(("completed", result, request.sequence))
                request = None
                continue
            raise AssertionError("Unknown fixture command: " + operation)
    except BaseException as error:
        connection.send(("error", repr(error)))
        raise
    finally:
        if address is not None:
            library.MGTTestMailboxUnmap(address)
        connection.close()


def abandoned_producer(connection, library_path, target_pid):
    """Crash after delivering raw bytes, before the resident owner can ACK."""
    mailbox = Hades2CommandMailbox(library_path, target_pid, alive=lambda: True)
    connection.send(("mapping", str(mailbox.path), mailbox.generation_hi, mailbox.generation_lo))
    if connection.recv() != "mapped":
        raise AssertionError("Consumer mapping was not installed")
    mailbox.installed_in_target()
    value = mailbox.execute("return 'accepted'")
    connection.send(("raw_result", value))
    os._exit(0)


class Consumer:
    def __init__(self, library_path):
        self.connection, child_connection = SPAWN.Pipe()
        self.process = SPAWN.Process(target=consumer_process,
                                     args=(child_connection, str(library_path)))
        self.process.start()
        child_connection.close()

    def install(self, mailbox):
        self.connection.send((str(mailbox.path), mailbox.generation_hi, mailbox.generation_lo))
        assert receive(self.connection) == ("mapped",)
        mailbox.installed_in_target()

    def send(self, operation, *arguments):
        self.connection.send((operation, *arguments))

    def receive(self):
        return receive(self.connection)

    def snapshot(self):
        self.send("inspect")
        message = self.receive()
        assert message[0] == "snapshot", message
        return message[1]

    def terminate(self):
        self.process.terminate()
        self.process.join(5)
        assert not self.process.is_alive()

    def close(self):
        if self.process.is_alive():
            self.send("stop")
            self.process.join(5)
            if self.process.is_alive():
                self.terminate()
        self.connection.close()


class Clock:
    """Advance only at deterministic cross-process barriers, without sleeps."""
    def __init__(self):
        self.now = 0.0
        self.barrier = None

    def __call__(self):
        return self.now

    def wait(self, duration):
        if self.barrier is not None:
            barrier, self.barrier = self.barrier, None
            barrier()
        self.now += duration


class MailboxClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which("cc")
        if compiler is None:
            raise AssertionError("A C compiler is required for mailbox client integration")
        cls.temporary = tempfile.TemporaryDirectory(prefix="mgt-mailbox-client-tests-")
        cls.library_path = Path(cls.temporary.name) / "mailbox.so"
        subprocess.run([
            compiler, "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic", "-O2",
            "-DMGT_MAILBOX_PORTABLE_TEST", "-fPIC",
            "-dynamiclib" if sys.platform == "darwin" else "-shared",
            "-I", str(ROOT / "Backend/games/hades2/native"),
            str(ROOT / "Backend/games/hades2/native/CommandMailbox.c"),
            str(ROOT / "tests/fixtures/hades2/mailbox_client.c"),
            "-o", str(cls.library_path),
        ], check=True)
        cls.native = fixture_library(cls.library_path)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def mailbox(self, *, clock=None):
        consumer = Consumer(self.library_path)
        self.addCleanup(consumer.close)
        keywords = {} if clock is None else {"clock": clock, "wait": clock.wait}
        mailbox = Hades2CommandMailbox(self.library_path, consumer.process.pid,
                                      alive=consumer.process.is_alive, **keywords)
        self.addCleanup(mailbox.close)
        consumer.install(mailbox)
        return mailbox, consumer

    def assert_error(self, code, operation):
        with self.assertRaises(AdapterError) as failure:
            operation()
        self.assertEqual(failure.exception.code, code)
        return failure.exception

    def assert_poisoned(self, mailbox):
        self.assertTrue(mailbox.tainted)
        self.assertEqual(inspect(self.native, mailbox.address)["flags"],
                         CLOSED_FLAG | POISONED_FLAG)
        self.assert_error("restart_required", lambda: mailbox.execute("must not execute"))

    def roundtrip(self, mailbox, consumer, reply=b'{"status":"ready"}', *, clock=None):
        consumer.send("roundtrip", SUCCESS, 0, reply)
        completed = []
        if clock is not None:
            clock.barrier = lambda: completed.append(consumer.receive())
        self.assertEqual(mailbox.execute("return status()"), reply.decode())
        if clock is not None:
            clock.barrier = None
        self.assertEqual((completed[0] if completed else consumer.receive())[0:2], ("completed", OK))

    def test_raw_success_waits_for_explicit_ack(self):
        mailbox, consumer = self.mailbox()
        self.assertFalse(mailbox.path.exists())
        self.roundtrip(mailbox, consumer, '{"text":"回执"}'.encode())
        profile = mailbox.last_profile
        self.assertGreater(profile["queueSeconds"], 0)
        self.assertEqual(profile["executionSeconds"], 0.000123)
        self.assertGreaterEqual(profile["roundTripSeconds"], profile["queueSeconds"])
        self.assertAlmostEqual(profile["overheadSeconds"], max(0.0, profile["roundTripSeconds"]
                               - profile["queueSeconds"] - profile["executionSeconds"]))
        before = consumer.snapshot()
        self.assertEqual((before["state"], before["claimed_count"]), (COMPLETE, 1))
        self.assert_error("mailbox_unacknowledged", lambda: mailbox.execute("second command"))
        self.assertEqual(consumer.snapshot(), before)
        mailbox.acknowledge()
        self.assertEqual(consumer.snapshot()["state"], IDLE)
        self.roundtrip(mailbox, consumer)
        self.assertEqual(consumer.snapshot()["highest_sequence"], 2)
        mailbox.acknowledge()

    def test_unknown_lua_marker_poison_preserves_unacknowledged_receipt(self):
        mailbox, consumer = self.mailbox()
        consumer.send("roundtrip", ERROR, 2,
                      b'[string "MacGamingTrainer"]:7: MGT_OUTCOME_UNKNOWN: action may have run')
        self.assert_error("outcome_unknown", lambda: mailbox.execute("native mutation"))
        self.assertEqual(consumer.receive()[0:2], ("completed", OK))
        self.assert_poisoned(mailbox)
        self.assertEqual(consumer.snapshot()["state"], COMPLETE)

    def test_known_lua_error_and_generation_rejection_are_acknowledged(self):
        for status, code in ((2, "lua_error"), (GENERATION_CHANGED, "resident_generation_missing")):
            with self.subTest(status=status):
                mailbox, consumer = self.mailbox()
                consumer.send("roundtrip", ERROR, status, b"Known pre-execution rejection")
                self.assert_error(code, lambda: mailbox.execute("rejected command"))
                self.assertEqual(consumer.receive()[0:2], ("completed", OK))
                snapshot = consumer.snapshot()
                self.assertEqual((snapshot["state"], snapshot["flags"]), (IDLE, 0))
                self.assertFalse(mailbox.tainted)
                self.roundtrip(mailbox, consumer)
                self.assertEqual(consumer.snapshot()["highest_sequence"], 2)
                mailbox.acknowledge()

    def test_interruption_before_claim_cancels_and_allows_next_command(self):
        clock = Clock()
        mailbox, consumer = self.mailbox(clock=clock)

        def interrupt():
            self.assertEqual(consumer.snapshot()["state"], POSTED)
            raise KeyboardInterrupt()

        clock.barrier = interrupt
        with self.assertRaises(KeyboardInterrupt):
            mailbox.execute("not yet consumed")
        snapshot = consumer.snapshot()
        self.assertEqual((snapshot["state"], snapshot["claimed_count"]), (IDLE, 0))
        self.assertFalse(mailbox.tainted)
        self.roundtrip(mailbox, consumer, clock=clock)
        mailbox.acknowledge()

    def test_unclaimed_timeout_is_known_cancelled_and_reusable(self):
        clock = Clock()
        mailbox, consumer = self.mailbox(clock=clock)
        self.assert_error("waiting", lambda: mailbox.execute("pending command", timeout_seconds=0.005))
        snapshot = consumer.snapshot()
        self.assertEqual((snapshot["state"], snapshot["claimed_count"], snapshot["flags"]),
                         (IDLE, 0, 0))
        self.assertFalse(mailbox.tainted)
        self.roundtrip(mailbox, consumer, clock=clock)
        self.assertEqual(consumer.snapshot()["highest_sequence"], 2)
        mailbox.acknowledge()

    def test_claimed_timeout_poison_survives_late_success(self):
        clock = Clock()
        mailbox, consumer = self.mailbox(clock=clock)
        consumer.send("claim")

        def claim_before_deadline():
            self.assertEqual(consumer.receive(), ("claimed", 1, b"slow command"))
            clock.now = 0.02

        clock.barrier = claim_before_deadline
        self.assert_error("outcome_unknown", lambda: mailbox.execute("slow command", timeout_seconds=0.01))
        self.assert_poisoned(mailbox)
        self.assertEqual(consumer.snapshot()["state"], EXECUTING)
        consumer.send("complete", SUCCESS, 0, b'{"result":"late"}')
        self.assertEqual(consumer.receive()[0:2], ("completed", OK))
        self.assertEqual(consumer.snapshot()["state"], COMPLETE)
        # Reading later or receiving a plausible result cannot renew this lease.
        self.assert_poisoned(mailbox)
        self.assertEqual(consumer.snapshot()["claimed_count"], 1)

    def test_interruption_after_claim_permanently_poisoned(self):
        clock = Clock()
        mailbox, consumer = self.mailbox(clock=clock)
        consumer.send("claim")

        def interrupt_after_claim():
            self.assertEqual(consumer.receive()[0:2], ("claimed", 1))
            raise KeyboardInterrupt()

        clock.barrier = interrupt_after_claim
        with self.assertRaises(KeyboardInterrupt):
            mailbox.execute("interrupted mutation")
        self.assert_poisoned(mailbox)
        consumer.send("complete", SUCCESS, 0, b"late")
        self.assertEqual(consumer.receive()[0:2], ("completed", OK))
        self.assertEqual(consumer.snapshot()["state"], COMPLETE)
        self.assert_poisoned(mailbox)

    def test_invalid_utf8_overflow_and_invalid_success_status_are_unknown(self):
        cases = (
            ("invalid UTF-8", b"\xff\xfe", 0, OK),
            ("overflow", b"x" * (RESULT_CAPACITY + 1), 0, CAPACITY),
            ("invalid success status", b"{}", 7, OK),
        )
        for name, payload, status, complete_result in cases:
            with self.subTest(name=name):
                mailbox, consumer = self.mailbox()
                consumer.send("roundtrip", SUCCESS, status, payload)
                self.assert_error("outcome_unknown", lambda: mailbox.execute("mutation"))
                self.assertEqual(consumer.receive()[0:2], ("completed", complete_result))
                self.assert_poisoned(mailbox)
                self.assertEqual(consumer.snapshot()["state"], COMPLETE)

    def test_contradictory_error_and_cancelled_receipts_keep_trust_poisoned(self):
        cases = (
            ("error with success status", ERROR, 0, b"error", 123_000),
            ("cancellation with error status", CANCELLED, 7, b"", 0),
            ("cancellation with result bytes", CANCELLED, 0, b"executed", 0),
            ("cancellation with execution time", CANCELLED, 0, b"", 123_000),
        )
        for name, outcome, status, payload, execution_ns in cases:
            with self.subTest(name=name):
                mailbox, consumer = self.mailbox()
                consumer.send("roundtrip", outcome, status, payload, execution_ns)
                self.assert_error("outcome_unknown", lambda: mailbox.execute("mutation"))
                self.assertEqual(consumer.receive()[0:2], ("completed", OK))
                self.assert_poisoned(mailbox)
                snapshot = consumer.snapshot()
                self.assertEqual((snapshot["state"], snapshot["claimed_count"]), (COMPLETE, 1))

    def test_target_exit_before_publication_leaves_slot_unused(self):
        mailbox, consumer = self.mailbox()
        consumer.terminate()
        self.assert_error("disconnected", lambda: mailbox.execute("must not publish"))
        snapshot = inspect(self.native, mailbox.address)
        self.assertEqual((snapshot["state"], snapshot["highest_sequence"], snapshot["flags"]),
                         (IDLE, 0, 0))
        self.assertFalse(mailbox.tainted)

    def test_target_exit_is_known_only_when_cancellation_beats_claim(self):
        for claimed in (False, True):
            with self.subTest(claimed=claimed):
                clock = Clock()
                mailbox, consumer = self.mailbox(clock=clock)
                if claimed:
                    consumer.send("claim")

                def exit_target():
                    if claimed:
                        self.assertEqual(consumer.receive()[0:2], ("claimed", 1))
                    else:
                        self.assertEqual(consumer.snapshot()["state"], POSTED)
                    consumer.terminate()
                    clock.now = 0.1

                clock.barrier = exit_target
                self.assert_error("outcome_unknown" if claimed else "disconnected",
                                  lambda: mailbox.execute("command during target exit"))
                snapshot = inspect(self.native, mailbox.address)
                self.assertEqual(snapshot["claimed_count"], int(claimed))
                if claimed:
                    self.assert_poisoned(mailbox)
                    self.assertEqual(snapshot["state"], EXECUTING)
                else:
                    self.assertFalse(mailbox.tainted)
                    self.assertEqual((snapshot["state"], snapshot["flags"]), (IDLE, 0))

    def test_producer_close_preserves_unacknowledged_consumer_mapping(self):
        mailbox, consumer = self.mailbox()
        self.roundtrip(mailbox, consumer)
        mailbox.close()
        snapshot = consumer.snapshot()
        self.assertEqual((snapshot["state"], snapshot["flags"]), (COMPLETE, CLOSED_FLAG))
        consumer.send("try_claim")
        self.assertEqual(consumer.receive(), ("claim_result", CLOSED))
        self.assert_error("disconnected", lambda: mailbox.execute("closed producer"))

    def test_producer_crash_after_raw_result_keeps_native_receipt_unacknowledged(self):
        connection, child_connection = SPAWN.Pipe()
        producer = SPAWN.Process(target=abandoned_producer,
                                 args=(child_connection, str(self.library_path), os.getpid()))
        address = None
        path = None
        producer.start()
        child_connection.close()
        try:
            message = receive(connection)
            self.assertEqual(message[0], "mapping")
            _, path, hi, lo = message
            address = self.native.MGTTestMailboxMap(os.fsencode(path), hi, lo)
            self.assertTrue(address)
            connection.send("mapped")
            request = Request()
            deadline = time.monotonic() + 5
            while self.native.MGTTestMailboxClaim(address, ctypes.byref(request)) != OK:
                if time.monotonic() >= deadline:
                    self.fail("Producer did not publish before exit")
                time.sleep(0.0001)
            self.assertEqual(ctypes.string_at(request.source, request.length), b"return 'accepted'")
            result = self.native.MGTTestMailboxComplete(address, request.sequence, SUCCESS, 0,
                                                        ctypes.c_char_p(b"accepted"), 8, 100)
            self.assertEqual(result, OK)
            self.assertEqual(receive(connection), ("raw_result", "accepted"))
            producer.join(5)
            self.assertEqual(producer.exitcode, 0)
            self.assertFalse(Path(path).exists())
            snapshot = inspect(self.native, address)
            self.assertEqual((snapshot["state"], snapshot["highest_sequence"], snapshot["claimed_count"]),
                             (COMPLETE, 1, 1))
            # A newly arriving consumer cannot claim this terminal request.
            self.assertEqual(self.native.MGTTestMailboxClaim(address, ctypes.byref(request)), EMPTY)
        finally:
            if producer.is_alive():
                producer.terminate()
            producer.join(5)
            connection.close()
            if address:
                self.native.MGTTestMailboxUnmap(address)
            if path is not None:
                shutil.rmtree(Path(path).parent)


if __name__ == "__main__":
    unittest.main()
