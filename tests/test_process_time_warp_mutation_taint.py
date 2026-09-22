from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from core.process_time_warp import LLDBProcessTimeWarpDriver, ProcessTimeWarpError


class FakeError:
    def __init__(self, failed=False):
        self.failed = failed

    def Fail(self):
        return self.failed

    def __str__(self):
        return "fake expression acknowledgement failure"


class FakeExpressionOptions:
    def SetLanguage(self, value):
        pass

    def SetTimeoutInMicroSeconds(self, value):
        pass

    def SetIgnoreBreakpoints(self, value):
        pass

    def SetUnwindOnError(self, value):
        pass


class FakeAddress:
    def __init__(self, value):
        self.value = value

    def GetLoadAddress(self, target):
        return self.value


class FakeSymbol:
    def __init__(self, value):
        self.value = value

    def IsValid(self):
        return True

    def GetStartAddress(self):
        return FakeAddress(self.value)


class FakeModule:
    def FindSymbol(self, name, symbol_type):
        return FakeSymbol(0x4000)


class FakeTarget:
    def GetNumModules(self):
        return 1

    def GetModuleAtIndex(self, index):
        return FakeModule()


class FakeResult:
    def __init__(self, failed):
        self.error = FakeError(failed)

    def GetError(self):
        return self.error

    def GetValueAsSigned(self):
        return 0


class FakeFrame:
    def __init__(self, failed):
        self.failed = failed
        self.expressions = []

    def EvaluateExpression(self, expression, options):
        self.expressions.append(expression)
        return FakeResult(self.failed)


class FakeThread:
    def __init__(self, frame):
        self.frame = frame

    def IsValid(self):
        return True

    def GetNumFrames(self):
        return 1

    def GetFrameAtIndex(self, index):
        return self.frame


class FakeProcess:
    def __init__(self, frame):
        self.frame = frame
        self.deallocated = []

    def GetState(self):
        return 5

    def GetSelectedThread(self):
        return FakeThread(self.frame)

    def AllocateMemory(self, size, permissions, error):
        return 0x1000

    def WriteMemory(self, address, payload, error):
        return len(payload)

    def DeallocateMemory(self, address):
        self.deallocated.append(address)


class FakeTransport:
    def __init__(self, failed=True):
        self.pid = 77
        self.tainted = False
        self.frame = FakeFrame(failed)
        self.process = FakeProcess(self.frame)
        self.target = FakeTarget()
        self.stop_calls = 0
        self.resume_calls = 0

    def alive(self):
        return True

    def stop(self, deadline):
        self.stop_calls += 1

    def resume(self, deadline):
        self.resume_calls += 1


class FakeLLDB:
    eStateStopped = 5
    eSymbolTypeCode = 1
    LLDB_INVALID_ADDRESS = -1
    eLanguageTypeC_plus_plus = 2
    ePermissionsReadable = 1
    ePermissionsWritable = 2
    SBExpressionOptions = FakeExpressionOptions
    SBError = FakeError


def expect_error(call, code):
    try:
        call()
    except ProcessTimeWarpError as error:
        assert error.code == code, (error.code, code)
    else:
        raise AssertionError(f"expected {code}")


# Read acknowledgement failures do not imply that target state mutated.
read_transport = FakeTransport(failed=True)
read_driver = LLDBProcessTimeWarpDriver(read_transport, lldb_module=FakeLLDB)
expect_error(read_driver.get_speed, "time_warp_call_failed")
assert read_transport.tainted is False

# MGTTimeWarpSetSpeed can execute before LLDB loses its acknowledgement. The
# caller must stop trusting the transport instead of reporting a retryable
# ordinary call failure.
set_transport = FakeTransport(failed=True)
set_driver = LLDBProcessTimeWarpDriver(set_transport, lldb_module=FakeLLDB)
expect_error(lambda: set_driver.set_speed(2.0), "outcome_unknown")
assert set_transport.tainted is True
expect_error(lambda: set_driver.session().__enter__(), "restart_required")
assert set_transport.stop_calls == 0, "tainted session touched the target before rejecting reuse"

# Installation has the same uncertainty once the mutating helper expression is
# evaluated. Scratch cleanup is still allowed because it does not repeat the
# helper mutation.
install_transport = FakeTransport(failed=True)
install_driver = LLDBProcessTimeWarpDriver(install_transport, lldb_module=FakeLLDB)
expect_error(lambda: install_driver.install(b"Hades II", 2.0), "outcome_unknown")
assert install_transport.tainted is True
assert install_transport.process.deallocated == [0x1000]

print("process_time_warp_mutation_taint_ok")
