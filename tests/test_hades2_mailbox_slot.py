"""Portable contract for the disabled Hades II shared-memory mailbox prototype.

No Hades process, real save data, LLDB injection or runtime code is executed.
The C handler stands in for a future game-main-thread pump; that native hook
must be proven separately before any production command uses this protocol.
"""
import ctypes
import mmap
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "Backend/games/hades2/native/MailboxSlot.c"
HI, LO = 0x7C9E_2871_C342_D59F, 0x4197_B352_E082_2C41
OTHER_HI = HI ^ 0x12345
IDLE, POSTED, EXECUTING, COMPLETE = 0, 2, 3, 4
UNKNOWN = 2
HANDLER = ctypes.CFUNCTYPE(
    ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p,
    ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32), ctypes.c_void_p,
)


def load_library(directory):
    clang = shutil.which("clang") or shutil.which("cc")
    assert clang is not None, "Mailbox contract requires a C11 compiler"
    library = Path(directory) / ("mailbox.dylib" if sys.platform == "darwin" else "mailbox.so")
    subprocess.run(
        [clang, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
         "-dynamiclib" if sys.platform == "darwin" else "-shared",
         "-fPIC", str(SOURCE), "-o", str(library)],
        check=True, capture_output=True, text=True,
    )
    lib = ctypes.CDLL(str(library))
    void = ctypes.c_void_p
    u32 = ctypes.c_uint32
    u64 = ctypes.c_uint64
    lib.MGTMailboxABI.restype = u32
    lib.MGTMailboxSize.restype = ctypes.c_size_t
    lib.MGTMailboxInit.argtypes = [void, ctypes.c_size_t, u64, u64]
    lib.MGTMailboxInit.restype = ctypes.c_int
    lib.MGTMailboxPhase.argtypes = [void, u64, u64]
    lib.MGTMailboxPhase.restype = u32
    lib.MGTMailboxSubmit.argtypes = [void, u64, u64, u64, void, u32]
    lib.MGTMailboxSubmit.restype = ctypes.c_int
    lib.MGTMailboxPump.argtypes = [void, u64, u64, HANDLER, void]
    lib.MGTMailboxPump.restype = ctypes.c_int
    lib.MGTMailboxRead.argtypes = [
        void, u64, u64, u64, void, u32,
        ctypes.POINTER(u32), ctypes.POINTER(u32),
    ]
    lib.MGTMailboxRead.restype = ctypes.c_int
    lib.MGTMailboxAck.argtypes = [void, u64, u64, u64]
    lib.MGTMailboxAck.restype = ctypes.c_int
    return lib


class Slot:
    def __init__(self, lib, hi=HI, lo=LO):
        self.lib = lib
        self.hi, self.lo = hi, lo
        self.mapping = mmap.mmap(-1, lib.MGTMailboxSize(),
                                  flags=mmap.MAP_SHARED,
                                  prot=mmap.PROT_READ | mmap.PROT_WRITE)
        self.address = ctypes.c_void_p(ctypes.addressof(ctypes.c_char.from_buffer(self.mapping)))
        assert lib.MGTMailboxInit(self.address, lib.MGTMailboxSize(), self.hi, self.lo) == 0

    def phase(self):
        return self.lib.MGTMailboxPhase(self.address, self.hi, self.lo)

    def submit(self, request_id, payload):
        return self.lib.MGTMailboxSubmit(self.address, self.hi, self.lo, request_id,
                                          ctypes.c_char_p(payload), len(payload))

    def read(self, request_id, capacity=128):
        output = ctypes.create_string_buffer(capacity)
        length, outcome = ctypes.c_uint32(99), ctypes.c_uint32(99)
        result = self.lib.MGTMailboxRead(
            self.address, self.hi, self.lo, request_id, output, capacity,
            ctypes.byref(length), ctypes.byref(outcome),
        )
        return result, output.raw[:length.value] if result == 0 else None, outcome.value

    def ack(self, request_id):
        return self.lib.MGTMailboxAck(self.address, self.hi, self.lo, request_id)


with tempfile.TemporaryDirectory(prefix="mgt-mailbox-slot-") as temporary:
    lib = load_library(temporary)
    assert lib.MGTMailboxABI() == 1
    slot = Slot(lib)
    assert slot.phase() == IDLE
    assert lib.MGTMailboxInit(slot.address, lib.MGTMailboxSize(), HI, LO) < 0
    assert lib.MGTMailboxPhase(slot.address, OTHER_HI, LO) == 0xFFFFFFFF
    assert lib.MGTMailboxSubmit(slot.address, OTHER_HI, LO, 1, ctypes.c_char_p(b"x"), 1) < 0
    assert slot.submit(0, b"x") < 0
    assert slot.submit(1, b"") < 0
    assert slot.submit(1, b"x" * (65536 + 1)) < 0
    assert slot.phase() == IDLE
    assert slot.submit(1, b"a\0b") == 0
    assert slot.phase() == POSTED
    assert slot.submit(2, b"later") < 0, "Unacknowledged slot was overwritten"

    observed = []
    @HANDLER
    def echo(input_buffer, input_len, output_buffer, capacity, length, context):
        data = ctypes.string_at(input_buffer, input_len)
        observed.append(data)
        assert len(data) <= capacity
        ctypes.memmove(output_buffer, data, len(data))
        length[0] = len(data)
        return 0

    assert lib.MGTMailboxPump(slot.address, HI, LO, echo, None) == 1
    assert lib.MGTMailboxPump(slot.address, HI, LO, echo, None) == 0
    assert observed == [b"a\0b"], "Same request executed more than once"
    assert slot.phase() == COMPLETE
    assert slot.read(2)[0] < 0, "Wrong request ID read a completed result"
    assert slot.read(1, 2)[0] < 0, "Partial result buffer was treated as complete"
    assert slot.ack(1) < 0, "Incomplete result was acknowledged"
    assert slot.read(1) == (0, b"a\0b", 0)
    assert lib.MGTMailboxAck(slot.address, OTHER_HI, LO, 1) < 0
    assert slot.ack(2) < 0
    assert slot.ack(1) == 0
    assert slot.phase() == IDLE
    assert slot.ack(1) < 0
    assert slot.read(1)[0] < 0
    assert slot.submit(1, b"duplicate") < 0, "Ack forgot the accepted ID"
    assert slot.submit(2, b"ok") == 0
    if sys.platform == "darwin":
        off_thread_result = []
        thread = threading.Thread(target=lambda: off_thread_result.append(
            lib.MGTMailboxPump(slot.address, HI, LO, echo, None)))
        thread.start()
        thread.join(timeout=2)
        assert not thread.is_alive() and off_thread_result == [-3]
        assert slot.phase() == POSTED, "Foreign thread consumed game-thread work"
    assert lib.MGTMailboxPump(slot.address, HI, LO, echo, None) == 1
    assert slot.ack(2) < 0, "Unobserved result was acknowledged"
    assert slot.read(2) == (0, b"ok", 0)
    assert slot.ack(2) == 0

    # Malformed handler receipts cannot be converted to a successful mutation.
    @HANDLER
    def malformed(input_buffer, input_len, output_buffer, capacity, length, context):
        length[0] = capacity + 1
        return 0
    assert slot.submit(3, b"write") == 0
    assert lib.MGTMailboxPump(slot.address, HI, LO, malformed, None) == 1
    assert slot.read(3) == (0, b"", UNKNOWN)
    assert slot.submit(4, b"retry before acknowledgement") < 0
    assert slot.ack(3) < 0, "Outcome-unknown must terminalize this generation"
    assert slot.submit(3, b"retry same ID") < 0

    slot = Slot(lib, OTHER_HI, LO)  # Explicit fresh mapping/nonce after unknown.
    @HANDLER
    def known_failure(input_buffer, input_len, output_buffer, capacity, length, context):
        message = b"known failure"
        ctypes.memmove(output_buffer, message, len(message))
        length[0] = len(message)
        return 1
    assert slot.submit(1, b"reject") == 0
    assert lib.MGTMailboxPump(slot.address, slot.hi, slot.lo, known_failure, None) == 1
    assert slot.read(1) == (0, b"known failure", 1)
    assert slot.ack(1) == 0
    assert slot.submit(1, b"retry duplicate") < 0

    # A posted, possibly crossed request cannot be canceled with an ordinary
    # submit or replaced by another generation in the same live mapping.
    assert slot.submit(2, b"abandoned") == 0
    assert slot.phase() == POSTED
    assert slot.submit(3, b"must block") < 0
    assert lib.MGTMailboxInit(slot.address, lib.MGTMailboxSize(), HI, LO) < 0
    assert lib.MGTMailboxPump(slot.address, HI, LO, echo, None) < 0
    assert slot.phase() == POSTED

    # Verify actual inter-process release/acquire visibility: parent publishes
    # the slot; a separate process performs the callback and publishes receipt.
    shared = Slot(lib)
    pid = os.fork() if hasattr(os, "fork") else None
    if pid == 0:
        try:
            deadline = time.monotonic() + 2.5
            while time.monotonic() < deadline:
                if lib.MGTMailboxPump(shared.address, HI, LO, echo, None) == 1:
                    os._exit(0)
                time.sleep(0.001)
            os._exit(8)
        except BaseException:
            os._exit(9)
    elif pid is not None:
        assert shared.submit(17, b"across-process") == 0
        deadline = time.monotonic() + 2.5
        while shared.phase() != COMPLETE and time.monotonic() < deadline:
            time.sleep(0.001)
        assert shared.read(17) == (0, b"across-process", 0)
        waited, result = os.waitpid(pid, 0)
        assert waited == pid and os.WIFEXITED(result) and os.WEXITSTATUS(result) == 0
        assert shared.ack(17) == 0
        assert shared.submit(17, b"duplicate across process") < 0
    else:
        print("mailbox fork cross-process probe skipped (platform has no fork)")

print("hades2_mailbox_slot_ok")
