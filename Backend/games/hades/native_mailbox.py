"""Load and install the universal x86_64/arm64 Hades I command mailbox."""
from dataclasses import dataclass
from pathlib import Path
import struct
import sys
import time

from core.adapter import AdapterError
from .operation_budgets import (
    EXPRESSION_TIMEOUT_MICROSECONDS,
    PROCESS_CONTROL_TIMEOUT_SECONDS,
)


# These values mirror MGTMailboxInstallStatus in native/MailboxProtocol.h.
INSTALL_SUCCESS = 0
INSTALL_FAILURE = -1
INSTALL_RESTART_REQUIRED = -2

FAT_MAGIC = 0xCAFEBABE
MH_MAGIC_64 = 0xFEEDFACF
CPU_TYPE_X86_64 = 0x01000007
CPU_TYPE_ARM64 = 0x0100000C
MH_DYLIB = 6
LC_UUID = 0x1B

# Instruction boundary immediately after `subq $0x58, %rsp` in sgg::HadesApp::Update(float),
# outside the verified 16-byte entry prologue so the stack frame is established.
HADES_APP_UPDATE_RENDEZVOUS_OFFSET = 0x11


def _macho64_uuid(data, *, target_cputype):
    if len(data) < 32:
        raise ValueError('Incomplete native Mach-O slice')
    magic, cpu, _, kind, count, size, _, _ = struct.unpack_from('<8I', data)
    if magic != MH_MAGIC_64 or cpu != target_cputype or kind != MH_DYLIB or size > len(data) - 32:
        raise ValueError(f'Native slice is not a 64-bit Mach-O dylib for cputype 0x{target_cputype:x}')
    cursor, end = 32, 32 + size
    for _ in range(count):
        if cursor + 8 > end:
            break
        command, length = struct.unpack_from('<II', data, cursor)
        if length < 8 or cursor + length > end:
            break
        if command == LC_UUID and length == 24:
            return data[cursor + 8:cursor + 24].hex().upper()
        cursor += length
    raise ValueError('Native Mach-O slice has no valid LC_UUID')


def slice_uuid(path, *, target_cputype=CPU_TYPE_X86_64):
    """Return the uppercase hex UUID (without dashes) of a Mach-O slice in a thin or Fat dylib."""
    data = Path(path).read_bytes()
    if len(data) < 8:
        raise ValueError('Incomplete native image')
    be_magic, nfat_arch = struct.unpack_from('>II', data)
    if be_magic == FAT_MAGIC:
        if nfat_arch == 0 or nfat_arch > 16 or 8 + nfat_arch * 20 > len(data):
            raise ValueError('Invalid universal Mach-O header')
        for index in range(nfat_arch):
            cputype, _, offset, size, _ = struct.unpack_from('>5I', data, 8 + index * 20)
            if cputype == target_cputype:
                if size < 32 or offset > len(data) or size > len(data) - offset:
                    raise ValueError('Truncated universal Mach-O slice')
                return _macho64_uuid(data[offset:offset + size], target_cputype=target_cputype)
        raise ValueError(f'Universal Mach-O does not contain required slice 0x{target_cputype:x}')
    return _macho64_uuid(data, target_cputype=target_cputype)


def _check_install_status(status, message, mailbox, transport):
    if status == INSTALL_SUCCESS:
        return
    if status == INSTALL_RESTART_REQUIRED:
        mailbox.poison()
        transport.tainted = True
        raise AdapterError(
            'restart_required', 'hades.error.restartRequired',
            diagnostic=f'Native mailbox install status={status}: {message}',
        )
    raise AdapterError(
        'incompatible', 'hades.error.unsupportedBuild',
        diagnostic=f'Native mailbox install status={status}: {message}',
    )


def _raise_install_unreturned(error, mailbox, transport, *, phase_bytes, phase_read_failed):
    mailbox.poison()
    transport.tainted = True
    if phase_read_failed or phase_bytes not in (b'\x00', b'\x02'):
        transport._unsafe_vm_pid = transport.pid
        raise AdapterError(
            'outcome_unknown', 'hades.error.luaInterrupted',
            diagnostic='Mailbox installation interrupted inside Lua: ' + str(error),
        )
    raise AdapterError(
        'restart_required', 'hades.error.restartRequired',
        diagnostic='Mailbox installation did not return: ' + str(error),
    )


@dataclass(frozen=True)
class CommandMailboxLibrary:
    path: Path
    target_header_base: int
    installer: int
    main_update: int


def _resolve_unique_symbol(target, module, lldb, name):
    addresses = set()
    for candidate in (name, '_' + name):
        matches = module.FindSymbols(candidate, lldb.eSymbolTypeCode)
        for index in range(matches.GetSize()):
            symbol = matches.GetContextAtIndex(index).GetSymbol()
            if symbol.IsValid():
                address = symbol.GetStartAddress().GetLoadAddress(target)
                if address not in (0, lldb.LLDB_INVALID_ADDRESS):
                    addresses.add(address)
    if len(addresses) != 1:
        raise ValueError('Native library export is missing or ambiguous: ' + name)
    return addresses.pop()


def prepare_command_mailbox(transport, lldb):
    """Load the universal mailbox dylib into the verified stopped Hades x86_64 target."""
    path = (Path(__file__).with_name('native') / 'libMGTHadesCommandMailbox.dylib').resolve(strict=True)
    try:
        game_module = transport.target.GetModuleAtIndex(0)
        expected_game_uuid = transport.supported_build['uuid']
        if not game_module.IsValid() or game_module.GetUUIDString() != expected_game_uuid:
            raise ValueError('Native mailbox requires the verified Hades build')
        base = game_module.GetObjectFileHeaderAddress().GetLoadAddress(transport.target)
        if base in (0, lldb.LLDB_INVALID_ADDRESS):
            raise ValueError('Cannot locate the verified Hades image header')
        expected_uuid = slice_uuid(path, target_cputype=CPU_TYPE_X86_64)
        spec = lldb.SBFileSpec(str(path))
        module = transport.target.FindModule(spec)
        if not module.IsValid():
            error = lldb.SBError()
            token = transport.process.LoadImage(spec, error)
            if error.Fail() or token == lldb.LLDB_INVALID_IMAGE_TOKEN:
                raise ValueError('Cannot load Hades command mailbox library: ' + str(error))
            module = transport.target.FindModule(spec)
        if not module.IsValid() or (module.GetUUIDString() or '').replace('-', '').upper() != expected_uuid:
            raise ValueError('Loaded Hades command mailbox differs from packaged image; restart Hades')
        _resolve_unique_symbol(transport.target, module, lldb, 'MGTMailboxABI')
        installer = _resolve_unique_symbol(transport.target, module, lldb, 'MGTCommandMailboxInstall')
        update_entry = transport.addresses['_ZN3sgg8HadesApp6UpdateEf'] + HADES_APP_UPDATE_RENDEZVOUS_OFFSET
        return CommandMailboxLibrary(path, base, installer, update_entry)
    except (OSError, ValueError, KeyError) as error:
        raise AdapterError(
            'incompatible', 'hades.error.unsupportedBuild', diagnostic=str(error),
        ) from error


def install_command_mailbox(transport, lldb, mailbox, library):
    """Install the shared-memory slot and __DATA vtable hook at an idle main-thread boundary."""
    if getattr(transport, 'cleanup_pending', False):
        raise transport._quarantined_error()
    if getattr(transport, 'tainted', False):
        raise AdapterError('restart_required', 'hades.error.restartRequired')
    scratch = None
    transport._boundary_initial_stop_pending = False
    try:
        thread, state = transport._boundary(entry_address=library.main_update, touch_focus=False)
        path_bytes = str(mailbox.path).encode('utf-8') + b'\0'
        capacity = 4096
        error = lldb.SBError()
        scratch = transport.process.AllocateMemory(
            len(path_bytes) + 1 + capacity,
            lldb.ePermissionsReadable | lldb.ePermissionsWritable,
            error,
        )
        if error.Fail() or not scratch:
            raise AdapterError('memory_error', 'hades.error.debuggerCall', diagnostic=str(error))
        if transport.process.WriteMemory(scratch, path_bytes, error) != len(path_bytes) or error.Fail():
            raise AdapterError('memory_error', 'hades.error.debuggerCall', diagnostic=str(error))
        phase_addr = scratch + len(path_bytes)
        out_addr = phase_addr + 1
        if transport.process.WriteMemory(phase_addr, b'\x00', error) != 1 or error.Fail():
            raise AdapterError('memory_error', 'hades.error.debuggerCall', diagnostic=str(error))
        installer = library.installer
        expression = (
            f'((int(*)(void*,unsigned long,const char*,unsigned long long,unsigned long long,'
            f'volatile unsigned char*,char*,unsigned long)){installer})'
            f'((void*){state},{library.target_header_base},(const char*){scratch},'
            f'{mailbox.generation_hi}ULL,{mailbox.generation_lo}ULL,'
            f'(volatile unsigned char*){phase_addr},(char*){out_addr},{capacity})'
        )
        options = lldb.SBExpressionOptions()
        options.SetLanguage(lldb.eLanguageTypeC_plus_plus)
        options.SetTimeoutInMicroSeconds(EXPRESSION_TIMEOUT_MICROSECONDS)
        options.SetIgnoreBreakpoints(True)
        options.SetUnwindOnError(True)
        options.SetStopOthers(True)
        options.SetTryAllThreads(False)
        result = thread.GetFrameAtIndex(0).EvaluateExpression(expression, options)
        if result.GetError().Fail():
            phase_error = lldb.SBError()
            observed_phase = transport.process.ReadMemory(phase_addr, 1, phase_error)
            _raise_install_unreturned(
                result.GetError(), mailbox, transport,
                phase_bytes=observed_phase, phase_read_failed=phase_error.Fail(),
            )
        status = result.GetValueAsSigned()
        message = ''
        if status != INSTALL_SUCCESS:
            message = transport.process.ReadCStringFromMemory(out_addr, capacity, error)
            if error.Fail():
                message = 'Cannot read mailbox installation diagnostic'
        _check_install_status(status, message, mailbox, transport)
        mailbox.installed_in_target()
    finally:
        primary_error = sys.exc_info()[1]
        initial_stop_failed = getattr(transport, '_boundary_initial_stop_pending', False)
        transport._boundary_initial_stop_pending = False
        if not initial_stop_failed and (getattr(transport, 'vm_interrupted', False) or transport.alive()):
            try:
                if getattr(transport, 'vm_interrupted', False):
                    transport._terminate_interrupted_process()
                else:
                    transport._stop(time.monotonic() + PROCESS_CONTROL_TIMEOUT_SECONDS)
                    transport.target.DeleteAllBreakpoints()
                    transport._restore_focus()
                    if scratch is not None:
                        transport.process.DeallocateMemory(scratch)
                    transport._resume(time.monotonic() + PROCESS_CONTROL_TIMEOUT_SECONDS)
            except Exception as error:
                mailbox.poison()
                transport.tainted = True
                detail = getattr(error, 'diagnostic', None) or str(error)
                if primary_error is not None:
                    original = getattr(primary_error, 'diagnostic', None) or str(primary_error)
                    detail = original + '; cleanup: ' + detail
                key = 'luaTerminationFailed' if getattr(transport, 'vm_interrupted', False) else 'outcomeUnknown'
                raise AdapterError('outcome_unknown', 'hades.error.' + key, diagnostic=detail) from error
