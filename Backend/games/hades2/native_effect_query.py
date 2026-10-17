"""Load the persistent, exact-build Hades native query before Lua sampling."""
from dataclasses import dataclass
from pathlib import Path

from core.adapter import AdapterError
from .native_library import image_uuid as _image_uuid, load_native_library


@dataclass(frozen=True)
class NativeQueryLibrary:
    installer: int
    target_header_base: int


def prepare_native_query(transport, lldb):
    # Transport's symbol-based compatibility fallback cannot authorize offsets.
    if transport.runtime_uuid != transport.known_uuid:
        return None
    path = Path(__file__).with_name('native') / 'libMGTNativeEffectQuery.dylib'
    try:
        loaded = load_native_library(
            transport, lldb, path,
            abi_symbol='MGTNativeEffectQueryABI', abi_version=3,
            exports=('MGTNativeEffectQueryInstall',),
        )
        return NativeQueryLibrary(loaded.addresses['MGTNativeEffectQueryInstall'], loaded.target_header_base)
    except (OSError, ValueError) as error:
        raise AdapterError('incompatible', 'hades2.error.nativeQueryUnavailable', diagnostic=str(error)) from error
