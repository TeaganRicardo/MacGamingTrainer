"""Attach phase observations surround API calls without launching or attaching a game."""
import logging
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))

from core.adapter import AdapterError


class Error:
    failed = False

    def Fail(self):
        return self.failed

    def __str__(self):
        return 'fixture attach failure'


fake_lldb = SimpleNamespace(SBError=Error)
with patch.object(subprocess, 'check_output', return_value=''), \
     patch.dict(sys.modules, {'lldb': fake_lldb}):
    from games.hades2 import transport as transport_module


def run_case(mode):
    messages, calls = [], []

    def assert_in_phase(phase):
        begin = f'LLDBPhase phase={phase} event=begin'
        end = f'LLDBPhase phase={phase} event=end'
        assert begin in messages, messages
        assert not any(message.startswith(end) for message in messages), messages

    class Target:
        def AttachToProcessWithID(self, listener, pid, error):
            assert pid == 4242
            assert_in_phase('attach.AttachToProcessWithID')
            calls.append('attach')
            if mode == 'attach_raises':
                raise RuntimeError('fixture attach exception')
            error.failed = mode == 'attach_denied'
            return SimpleNamespace()

        def GetModuleAtIndex(self, index):
            assert index == 0
            return SimpleNamespace(GetUUIDString=lambda: 'verified-target')

        def GetTriple(self):
            return 'arm64-apple-macosx'

    target = Target()
    transport = transport_module.Hades2LuaTransport.__new__(transport_module.Hades2LuaTransport)
    transport.process = None
    transport.listener = object()
    transport.debugger = SimpleNamespace(CreateTarget=lambda path: target)
    transport.symbols = {}
    transport.known_uuid = 'verified-target'

    def resume(deadline):
        assert 0 < deadline - time.monotonic() <= 3
        assert_in_phase('attach.resume')
        calls.append('resume')
        if mode == 'resume_raises':
            raise RuntimeError('fixture resume exception')

    with patch.object(logging, 'info', side_effect=lambda message, *args: messages.append(message % args)), \
         patch.object(transport_module, 'prepare_native_query', return_value=None), \
         patch.object(transport, 'resume', side_effect=resume):
        try:
            transport.attach(4242)
        except (RuntimeError, AdapterError) as error:
            assert mode != 'success'
            if mode == 'attach_denied':
                assert error.code == 'attach_denied' and transport.process is None
            else:
                assert str(error) == ('fixture attach exception' if mode == 'attach_raises'
                                      else 'fixture resume exception')
        else:
            assert mode == 'success'
            assert transport.pid == 4242 and transport.tainted is False
    assert calls == (['attach', 'resume'] if mode in ('success', 'resume_raises') else ['attach'])
    for phase in ['attach.AttachToProcessWithID'] + (['attach.resume'] if 'resume' in calls else []):
        assert sum(message == f'LLDBPhase phase={phase} event=begin' for message in messages) == 1
        end = [message for message in messages if message.startswith(f'LLDBPhase phase={phase} event=end')]
        assert len(end) == 1 and 'duration=' in end[0], messages


for mode in ('success', 'attach_denied', 'attach_raises', 'resume_raises'):
    run_case(mode)

print('hades2_lldb_attach_phases_ok')
