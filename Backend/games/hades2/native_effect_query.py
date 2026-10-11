"""Load the persistent, exact-build Hades native query before Lua sampling."""
from pathlib import Path
import struct

from core.adapter import AdapterError


def _image_uuid(path):
    """The selected Hades module builds an arm64 thin Mach-O dylib."""
    data = path.read_bytes()
    if len(data) < 32:
        raise ValueError('Incomplete native query image')
    magic, cpu, _, kind, count, size, _, _ = struct.unpack_from('<8I', data)
    if magic != 0xFEEDFACF or cpu != 0x100000C or kind != 6 or size > len(data) - 32:
        raise ValueError('Native query image must be an arm64 Mach-O dylib')
    cursor, end = 32, 32 + size
    for _ in range(count):
        if cursor + 8 > end:
            break
        command, length = struct.unpack_from('<II', data, cursor)
        if length < 8 or cursor + length > end:
            break
        if command == 0x1B and length == 24:
            return data[cursor + 8:cursor + 24].hex().upper()
        cursor += length
    raise ValueError('Native query image has no valid UUID')


def prepare_native_query(transport, lldb):
    # Transport's symbol-based compatibility fallback cannot authorize offsets.
    if transport.runtime_uuid != transport.known_uuid:
        return None
    path = Path(__file__).with_name('native') / 'libMGTNativeEffectQuery.dylib'
    try:
        expected_uuid = _image_uuid(path)
        spec = lldb.SBFileSpec(str(path))
        module = transport.target.FindModule(spec)
        if not module.IsValid():
            error = lldb.SBError()
            token = transport.process.LoadImage(spec, error)
            if error.Fail() or token == lldb.LLDB_INVALID_IMAGE_TOKEN:
                raise ValueError('Cannot load native query: ' + str(error))
            module = transport.target.FindModule(spec)
        if not module.IsValid() or (module.GetUUIDString() or '').replace('-', '').upper() != expected_uuid:
            raise ValueError('Loaded native query does not match the packaged image; restart the game')

        def address(name):
            matches = module.FindSymbols(name, lldb.eSymbolTypeCode)
            addresses = set()
            for index in range(matches.GetSize()):
                symbol = matches.GetContextAtIndex(index).GetSymbol()
                if symbol.IsValid():
                    value = symbol.GetStartAddress().GetLoadAddress(transport.target)
                    if value not in (0, lldb.LLDB_INVALID_ADDRESS):
                        addresses.add(value)
            if len(addresses) != 1:
                raise ValueError('Native query export is missing or ambiguous: ' + name)
            return addresses.pop()

        abi, installer = address('MGTNativeEffectQueryABI'), address('MGTNativeEffectQueryInstall')
        # This pure ABI query does not touch Lua or the game world. Actual
        # registration happens in execute()'s leased MainThread expression.
        options = lldb.SBExpressionOptions()
        options.SetLanguage(lldb.eLanguageTypeC_plus_plus)
        options.SetStopOthers(True)
        options.SetTryAllThreads(False)
        options.SetTimeoutInMicroSeconds(2_000_000)
        options.SetIgnoreBreakpoints(True)
        options.SetUnwindOnError(True)
        result = transport.process.GetSelectedThread().GetFrameAtIndex(0).EvaluateExpression(
            f'((unsigned int(*)()){abi})()', options)
        if result.GetError().Fail() or result.GetValueAsUnsigned() != 1:
            raise ValueError('Native query ABI is incompatible: ' + str(result.GetError()))
        # Never unload: Lua can retain C callbacks after detach or re-register.
        return installer
    except (OSError, ValueError) as error:
        raise AdapterError('incompatible', 'hades2.error.nativeQueryUnavailable', diagnostic=str(error)) from error
