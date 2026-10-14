"""Helper identity/loading uses an isolated module, never a real game process."""
import struct
import logging
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))
from core.adapter import AdapterError
from games.hades2 import native_effect_query as query

UUID = bytes(range(16))
phase_logs = []


def phase_count(phase, event):
    prefix = f'LLDBPhase phase={phase} event={event}'
    return sum(message.startswith(prefix) for message in phase_logs)


class Error:
    def Fail(self): return False
    def __str__(self): return 'fixture'


class Options:
    def __getattr__(self, name):
        return lambda value: setattr(self, name.removeprefix('Set'), value)


class Module:
    valid = True
    uuid = UUID.hex()
    addresses = {'MGTNativeEffectQueryABI': [100], 'MGTNativeEffectQueryInstall': [200]}
    def IsValid(self): return self.valid
    def GetUUIDString(self): return self.uuid
    def FindSymbols(self, name, kind):
        addresses = self.addresses.get(name, [])
        return SimpleNamespace(GetSize=lambda: len(addresses), GetContextAtIndex=lambda index:
            SimpleNamespace(GetSymbol=lambda: SimpleNamespace(IsValid=lambda: True,
                GetStartAddress=lambda: SimpleNamespace(GetLoadAddress=lambda target: addresses[index]))))


class Target:
    def __init__(self, module):
        self.module = module
        self.game_uuid, self.game_base = 'supported', 0x100000000
    def FindModule(self, spec): return self.module
    def GetModuleAtIndex(self, index):
        assert index == 0
        return SimpleNamespace(IsValid=lambda: True, GetUUIDString=lambda: self.game_uuid,
            GetObjectFileHeaderAddress=lambda: SimpleNamespace(GetLoadAddress=lambda target: self.game_base))


class Process:
    def __init__(self, target): self.target, self.loaded, self.options, self.abi = target, 0, None, 3
    def LoadImage(self, spec, error):
        assert phase_count('prepareNative.LoadImage', 'begin') == phase_count('prepareNative.LoadImage', 'end') + 1
        self.loaded += 1
        self.target.module.valid = True
        return 1
    def GetSelectedThread(self):
        return SimpleNamespace(GetFrameAtIndex=lambda index: SimpleNamespace(EvaluateExpression=self.evaluate))
    def evaluate(self, expression, options):
        assert phase_count('prepareNative.ABI.EvaluateExpression', 'begin') == phase_count('prepareNative.ABI.EvaluateExpression', 'end') + 1
        self.options = options
        return SimpleNamespace(GetError=Error, GetValueAsUnsigned=lambda: self.abi)


lldb = SimpleNamespace(SBFileSpec=str, SBError=Error, SBExpressionOptions=Options,
    eSymbolTypeCode=1, eLanguageTypeC_plus_plus=2, LLDB_INVALID_IMAGE_TOKEN=-1, LLDB_INVALID_ADDRESS=-1)

with tempfile.TemporaryDirectory(prefix='mgt-query-loading-') as temporary:
    module_root = Path(temporary)
    native = module_root / 'native'; native.mkdir()
    image = native / 'libMGTNativeEffectQuery.dylib'
    image.write_bytes(struct.pack('<8I', 0xFEEDFACF, 0x100000C, 0, 6, 1, 24, 0, 0)
        + struct.pack('<II', 0x1B, 24) + UUID)
    assert query._image_uuid(image) == UUID.hex().upper()
    target = Target(Module()); process = Process(target)
    transport = SimpleNamespace(runtime_uuid='supported', known_uuid='supported', target=target, process=process)
    with patch.object(query, '__file__', str(module_root / 'native_effect_query.py')), \
         patch.object(logging, 'info', side_effect=lambda message, *args: phase_logs.append(message % args)):
        assert query.prepare_native_query(transport, lldb) == query.NativeQueryLibrary(200, target.game_base)
        assert process.loaded == 0, 'Reconnect reloaded an already matched image'
        assert process.options.StopOthers is True and process.options.TryAllThreads is False
        target.module.valid = False
        assert query.prepare_native_query(transport, lldb) == query.NativeQueryLibrary(200, target.game_base) and process.loaded == 1
        for process.abi in (1, 2):
            try:
                query.prepare_native_query(transport, lldb)
            except AdapterError as error:
                assert error.code == 'incompatible' and 'ABI' in error.diagnostic
            else:
                raise AssertionError('Old native library ABI was accepted')
        process.abi = 3
        for field, invalid in (('game_uuid', 'different-game'), ('game_base', 0), ('game_base', lldb.LLDB_INVALID_ADDRESS)):
            original = getattr(target, field)
            setattr(target, field, invalid)
            try:
                query.prepare_native_query(transport, lldb)
            except AdapterError as error:
                assert error.code == 'incompatible'
            else:
                raise AssertionError('Unverified game image authority was accepted')
            setattr(target, field, original)
        target.module.uuid = 'wrong'
        try:
            query.prepare_native_query(transport, lldb)
        except AdapterError as error:
            assert error.code == 'incompatible' and 'restart' in error.diagnostic
        else:
            raise AssertionError('Loaded image identity mismatch was accepted')
        target.module.uuid = UUID.hex()
        target.module.addresses = {**Module.addresses, 'MGTNativeEffectQueryInstall': [200, 300]}
        try:
            query.prepare_native_query(transport, lldb)
        except AdapterError as error:
            assert 'ambiguous' in error.diagnostic
        else:
            raise AssertionError('Ambiguous helper export was accepted')
        image.unlink()
        transport.runtime_uuid = 'future-build'
        assert query.prepare_native_query(transport, lldb) is None, 'Unknown game UUID reused native offsets'
        transport.runtime_uuid = 'supported'
        try:
            query.prepare_native_query(transport, lldb)
        except AdapterError as error:
            assert error.presentation == 'hades2.error.nativeQueryUnavailable'
        else:
            raise AssertionError('Missing package helper was accepted')
    for phase in ('prepareNative.LoadImage', 'prepareNative.ABI.EvaluateExpression'):
        assert phase_count(phase, 'begin') > 0
        assert phase_count(phase, 'begin') == phase_count(phase, 'end'), phase_logs
    image.write_bytes(b'not Mach-O')
    try:
        query._image_uuid(image)
    except ValueError:
        pass
    else:
        raise AssertionError('Invalid package image was accepted')
print('hades2_native_query_loading_ok')
