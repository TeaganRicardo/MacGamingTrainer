"""Install the game-thread mailbox once, behind the Hades debugger boundary."""
import time
from dataclasses import dataclass
from pathlib import Path

from core.adapter import AdapterError
from .native_library import load_native_library


@dataclass(frozen=True)
class CommandMailboxLibrary:
    path: Path
    target_header_base: int
    installer: int
    main_update: int


def prepare_command_mailbox(transport, lldb):
    path = Path(__file__).with_name("native") / "libMGTCommandMailbox.dylib"
    try:
        library = load_native_library(
            transport, lldb, path, abi_symbol="MGTMailboxABI", abi_version=1,
            exports=("MGTCommandMailboxInstall",),
        )
        # This entry runs before the game's focus/paused-world checks. The
        # native installer verifies its exact original (or already-owned) bytes.
        # Do not put its original prefix in the ordinary symbol manifest: the
        # process-lifetime hook is legitimately present on a later attachment.
        matches = transport.target.GetModuleAtIndex(0).FindSymbols(
            "_ZN3sgg3App6UpdateEf", lldb.eSymbolTypeCode,
        )
        addresses = set()
        for index in range(matches.GetSize()):
            symbol = matches.GetContextAtIndex(index).GetSymbol()
            if symbol.IsValid():
                address = symbol.GetStartAddress().GetLoadAddress(transport.target)
                if address not in (0, lldb.LLDB_INVALID_ADDRESS):
                    addresses.add(address)
        if len(addresses) != 1:
            raise ValueError("Hades main update entry is missing or ambiguous")
        # Rendezvous immediately after the four displaced instructions, where
        # the native trampoline resumes. The debugger lease must retain its
        # stop-reason identity through expression unwind, without overlapping
        # the bytes installed by the process-lifetime hook.
        return CommandMailboxLibrary(library.path, library.target_header_base,
                                     library.addresses["MGTCommandMailboxInstall"], addresses.pop() + 16)
    except (OSError, ValueError) as error:
        raise AdapterError("incompatible", "hades2.error.commandConnectionUnavailable",
                           diagnostic=str(error)) from error


def install_command_mailbox(transport, lldb, mailbox, library):
    """No resident command is submitted until this installation has completed."""
    scratch = None
    breakpoint = None
    try:
        thread, state, breakpoint = transport.boundary(entry_address=library.main_update)
        path = str(mailbox.path).encode("utf-8") + b"\0"
        capacity = 4096
        error = lldb.SBError()
        scratch = transport.process.AllocateMemory(
            len(path) + capacity, lldb.ePermissionsReadable | lldb.ePermissionsWritable, error,
        )
        if error.Fail() or not scratch:
            raise AdapterError("memory_error", "hades2.error.commandConnectionUnavailable", diagnostic=str(error))
        if transport.process.WriteMemory(scratch, path, error) != len(path) or error.Fail():
            raise AdapterError("memory_error", "hades2.error.commandConnectionUnavailable", diagnostic=str(error))
        query = transport.native_runtime_installer
        if query is None:
            raise AdapterError("incompatible", "hades2.error.commandConnectionUnavailable")
        out = scratch + len(path)
        installer = library.installer
        expression = (
            f"((int(*)(void*,unsigned long,const char*,unsigned long long,unsigned long long,"
            f"unsigned long,char*,unsigned long)){installer})"
            f"((void*){state},{library.target_header_base},(const char*){scratch},"
            f"{mailbox.generation_hi}ULL,{mailbox.generation_lo}ULL,"
            f"{query.installer},(char*){out},{capacity})"
        )
        options = lldb.SBExpressionOptions()
        options.SetLanguage(lldb.eLanguageTypeC_plus_plus)
        options.SetStopOthers(True)
        options.SetTryAllThreads(False)
        options.SetTimeoutInMicroSeconds(2_000_000)
        options.SetIgnoreBreakpoints(True)
        options.SetUnwindOnError(True)
        result = thread.GetFrameAtIndex(0).EvaluateExpression(expression, options)
        if result.GetError().Fail():
            mailbox.poison()
            transport.tainted = True
            raise AdapterError("restart_required", "hades2.error.restartRequired",
                               diagnostic="Mailbox installation did not return: " + str(result.GetError()))
        status = result.GetValueAsSigned()
        if status != 0:
            message = transport.process.ReadCStringFromMemory(out, capacity, error)
            if error.Fail():
                message = "Cannot read mailbox installation diagnostic"
            if status == -2:
                mailbox.poison()
                transport.tainted = True
            raise AdapterError("restart_required" if status == -2 else "incompatible",
                               "hades2.error.restartRequired" if status == -2
                               else "hades2.error.commandConnectionUnavailable",
                               diagnostic=f"Native mailbox install status={status}: {message}")
        mailbox.installed_in_target()
    finally:
        if breakpoint is not None and transport.target:
            transport.target.BreakpointDelete(breakpoint.GetID())
        if transport.process and transport.alive():
            try:
                transport.stop(time.monotonic() + 3, phase="mailbox.install_cleanup")
                transport.restore_focus()
                if scratch is not None:
                    transport.process.DeallocateMemory(scratch)
                transport.resume(time.monotonic() + 3)
            except BaseException:
                mailbox.poison()
                transport.tainted = True
                raise
