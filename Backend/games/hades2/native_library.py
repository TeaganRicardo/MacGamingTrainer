"""Exact-image loading for Hades-owned, process-lifetime native libraries."""
from dataclasses import dataclass
from pathlib import Path
import struct


def image_uuid(path):
    data = Path(path).read_bytes()
    if len(data) < 32:
        raise ValueError("Incomplete native image")
    magic, cpu, _, kind, count, size, _, _ = struct.unpack_from("<8I", data)
    if magic != 0xFEEDFACF or cpu != 0x100000C or kind != 6 or size > len(data) - 32:
        raise ValueError("Native image must be an arm64 Mach-O dylib")
    cursor, end = 32, 32 + size
    for _ in range(count):
        if cursor + 8 > end:
            break
        command, length = struct.unpack_from("<II", data, cursor)
        if length < 8 or cursor + length > end:
            break
        if command == 0x1B and length == 24:
            return data[cursor + 8:cursor + 24].hex().upper()
        cursor += length
    raise ValueError("Native image has no valid UUID")


@dataclass(frozen=True)
class LoadedNativeLibrary:
    path: Path
    target_header_base: int
    addresses: dict


def load_native_library(transport, lldb, path, *, abi_symbol, abi_version, exports):
    """Load only into the independently verified supported game, while stopped.

    Native callbacks can outlive a debugger attachment; an existing image must
    match the packaged UUID and is never unloaded to make a mismatch disappear.
    """
    if transport.runtime_uuid != transport.known_uuid:
        raise ValueError("Native library requires the supported Hades II image UUID")
    game_module = transport.target.GetModuleAtIndex(0)
    if not game_module.IsValid() or game_module.GetUUIDString() != transport.known_uuid:
        raise ValueError("Native library game image no longer matches the verified target")
    base = game_module.GetObjectFileHeaderAddress().GetLoadAddress(transport.target)
    if base in (0, lldb.LLDB_INVALID_ADDRESS):
        raise ValueError("Cannot locate the verified game image header")
    # dyld records canonical paths (for example /private/tmp on macOS).
    # Resolve the package alias before asking LLDB to match the loaded module.
    path = Path(path).resolve(strict=True)
    expected_uuid = image_uuid(path)
    spec = lldb.SBFileSpec(str(path))
    module = transport.target.FindModule(spec)
    if not module.IsValid():
        error = lldb.SBError()
        token = transport.process.LoadImage(spec, error)
        if error.Fail() or token == lldb.LLDB_INVALID_IMAGE_TOKEN:
            raise ValueError("Cannot load native library: " + str(error))
        module = transport.target.FindModule(spec)
    if not module.IsValid() or (module.GetUUIDString() or "").replace("-", "").upper() != expected_uuid:
        raise ValueError("Loaded native library differs from the packaged image; restart the game")
    addresses = {}
    for name in (abi_symbol, *exports):
        matches = module.FindSymbols(name, lldb.eSymbolTypeCode)
        values = set()
        for index in range(matches.GetSize()):
            symbol = matches.GetContextAtIndex(index).GetSymbol()
            if symbol.IsValid():
                value = symbol.GetStartAddress().GetLoadAddress(transport.target)
                if value not in (0, lldb.LLDB_INVALID_ADDRESS):
                    values.add(value)
        if len(values) != 1:
            raise ValueError("Native library export is missing or ambiguous: " + name)
        addresses[name] = values.pop()
    options = lldb.SBExpressionOptions()
    options.SetLanguage(lldb.eLanguageTypeC_plus_plus)
    options.SetStopOthers(True)
    options.SetTryAllThreads(False)
    options.SetTimeoutInMicroSeconds(2_000_000)
    options.SetIgnoreBreakpoints(True)
    options.SetUnwindOnError(True)
    result = transport.process.GetSelectedThread().GetFrameAtIndex(0).EvaluateExpression(
        f"((unsigned int(*)()){addresses[abi_symbol]})()", options,
    )
    if result.GetError().Fail() or result.GetValueAsUnsigned() != abi_version:
        raise ValueError("Native library ABI is incompatible: " + str(result.GetError()))
    return LoadedNativeLibrary(Path(path), base, addresses)
