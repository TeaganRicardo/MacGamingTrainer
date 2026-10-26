"""Exact-build x86_64 Hades Lua calls at the main-thread App::Update entry."""
import json
from pathlib import Path
import subprocess
import sys
import time

from core.adapter import AdapterError

sys.path.insert(0, subprocess.check_output(['/usr/bin/xcrun', 'lldb', '-P'], text=True).strip())
import lldb


def failure(code, key, detail=None):
    return AdapterError(code, 'hades.error.' + key, diagnostic=detail)


class HadesLuaTransport:
    def __init__(self):
        self.manifest = json.loads(Path(__file__).with_name('symbols.json').read_text())
        lldb.SBDebugger.Initialize()
        self.debugger = lldb.SBDebugger.Create()
        self.debugger.SetAsync(True)
        for setting, value in (
            ('symbols.enable-external-lookup', 'false'),
            ('target.preload-symbols', 'false'),
            ('target.load-script-from-symbol-file', 'false'),
            ('symbols.load-on-demand', 'true'),
        ):
            result = lldb.SBCommandReturnObject()
            self.debugger.GetCommandInterpreter().HandleCommand('settings set ' + setting + ' ' + value, result)
            if not result.Succeeded():
                raise failure('debugger_configuration', 'debuggerStart', result.GetError())
        self.listener = self.debugger.GetListener()
        self.target = None
        self.process = None
        self.pid = None
        self.addresses = {}
        self.focus_original = None
        self._tainted_pid = None
        self.tainted = False

    @property
    def tainted(self):
        return self._tainted_pid is not None

    @tainted.setter
    def tainted(self, value):
        self._tainted_pid = self.pid if value else None

    def _drain(self):
        event = lldb.SBEvent()
        while self.listener.GetNextEvent(event):
            pass

    def alive(self):
        self._drain()
        return self.process is not None and self.process.GetState() not in (
            lldb.eStateExited, lldb.eStateDetached, lldb.eStateInvalid,
        )

    def attach(self, pid, executable):
        if self.tainted and self._tainted_pid == pid:
            raise failure('restart_required', 'restartRequired')
        if self.alive() and self.pid == pid:
            return
        self.detach()
        self.target = self.debugger.CreateTarget('')
        error = lldb.SBError()
        self.process = self.target.AttachToProcessWithID(self.listener, pid, error)
        if error.Fail():
            self.process = None
            raise failure('attach_denied', 'attachDenied', str(error))
        self.pid = pid
        try:
            image = self.target.GetModuleAtIndex(0)
            image_path = Path(str(image.GetFileSpec())).resolve()
            if (image.GetUUIDString() != self.manifest['uuid']
                    or not self.target.GetTriple().startswith('x86_64-')
                    or image_path != Path(executable).resolve()):
                raise failure('incompatible', 'unsupportedBuild')
            base = image.GetObjectFileHeaderAddress().GetLoadAddress(self.target)
            if base == lldb.LLDB_INVALID_ADDRESS:
                raise failure('incompatible', 'unsupportedBuild')
            for name, spec in self.manifest['symbols'].items():
                address = base + spec['rva']
                if 'prefix' in spec:
                    expected = bytes.fromhex(spec['prefix'])
                    observed = self.process.ReadMemory(address, len(expected), error)
                    if error.Fail() or observed != expected:
                        raise failure('incompatible', 'unsupportedBuild', 'Function prefix mismatch: ' + name)
                self.addresses[name] = address
            self.tainted = False
            self._resume(time.monotonic() + 3)
        except Exception:
            self.detach()
            raise

    def stop(self, deadline):
        """Expose the transport's existing bounded stop to Core-owned helpers."""
        self._stop(deadline)

    def _stop(self, deadline):
        if not self.alive():
            raise failure('not_connected', 'notConnected')
        if self.process.GetState() == lldb.eStateStopped:
            return
        self.process.SendAsyncInterrupt()
        while time.monotonic() < deadline:
            self._drain()
            if self.process.GetState() == lldb.eStateStopped:
                return
            if not self.alive():
                raise failure('not_connected', 'notConnected')
            time.sleep(.005)
        raise failure('stop_timeout', 'stopTimeout')

    def _resume(self, deadline, *, breakpoint_expected=False):
        self._drain()
        if self.process.GetState() == lldb.eStateRunning:
            return
        previous_stop = self.process.GetStopID()
        error = self.process.Continue()
        if error.Fail():
            raise failure('resume_failed', 'resumeFailed', str(error))
        while time.monotonic() < deadline:
            self._drain()
            state = self.process.GetState()
            if state == lldb.eStateRunning:
                return
            if breakpoint_expected and state == lldb.eStateStopped and self.process.GetStopID() > previous_stop:
                return
            if not self.alive():
                raise failure('not_connected', 'notConnected')
            time.sleep(.005)
        raise failure('resume_timeout', 'resumeFailed')

    def resume(self, deadline):
        """Expose the transport's existing bounded resume to Core-owned helpers."""
        self._resume(deadline)

    def _restore_focus(self):
        if self.focus_original is None:
            return
        address = self.addresses['_ZN3sgg13ConfigOptions20RequireFocusToUpdateE']
        error = lldb.SBError()
        count = self.process.WriteMemory(address, self.focus_original, error)
        actual = self.process.ReadMemory(address, 1, error)
        if count != 1 or error.Fail() or actual != self.focus_original:
            raise failure('restore_failed', 'restoreFailed', str(error))
        self.focus_original = None

    def _boundary(self):
        deadline = time.monotonic() + 3
        self._stop(deadline)
        self._restore_focus()
        error = lldb.SBError()
        focus = self.addresses['_ZN3sgg13ConfigOptions20RequireFocusToUpdateE']
        self.focus_original = self.process.ReadMemory(focus, 1, error)
        if error.Fail() or self.focus_original not in (b'\x00', b'\x01'):
            self.focus_original = None
            raise failure('incompatible', 'unsupportedBuild')
        if self.process.WriteMemory(focus, b'\x00', error) != 1 or error.Fail():
            raise failure('memory_error', 'debuggerCall', str(error))
        breakpoint = self.target.BreakpointCreateByAddress(self.addresses['_ZN3sgg3App6UpdateEf'])
        self._resume(deadline, breakpoint_expected=True)
        while time.monotonic() < deadline:
            self._drain()
            if not self.alive():
                raise failure('not_connected', 'notConnected')
            if self.process.GetState() != lldb.eStateStopped:
                time.sleep(.005)
                continue
            matches = [thread for thread in self.process
                       if thread.GetStopReason() == lldb.eStopReasonBreakpoint
                       and thread.GetStopReasonDataAtIndex(0) == breakpoint.GetID()]
            if not matches:
                raise failure('unexpected_stop', 'unexpectedStop')
            thread = matches[0]
            state = self.process.ReadPointerFromMemory(
                self.addresses['_ZN3sgg13ScriptManager13LUA_INTERFACEE'], error,
            )
            if thread.GetName() == 'MainThread' and state and error.Success():
                breakpoint.SetEnabled(False)
                return thread, state
            self._resume(deadline, breakpoint_expected=True)
        raise failure('runtime_not_ready', 'runtimeNotReady')

    def execute(self, source, *, mutating=False):
        if self.tainted:
            raise failure('restart_required', 'restartRequired')
        payload = source.encode('utf-8')
        if len(payload) > 65536:
            raise ValueError('Hades Lua request exceeds 64 KiB')
        scratch = None
        try:
            thread, state = self._boundary()
            error = lldb.SBError()
            capacity = 262144
            scratch = self.process.AllocateMemory(len(payload) + 1 + capacity,
                lldb.ePermissionsReadable | lldb.ePermissionsWritable, error)
            if error.Fail() or not scratch:
                raise failure('memory_error', 'debuggerCall', str(error))
            if self.process.WriteMemory(scratch, payload + b'\0', error) != len(payload) + 1 or error.Fail():
                raise failure('memory_error', 'debuggerCall', str(error))
            output = scratch + len(payload) + 1
            addresses = self.addresses
            expression = f'''({{
              void *L=(void*){state}; char *o=(char*){output}; o[0]=0;
              int top=((int(*)(void*)){addresses['lua_gettop']})(L);
              int rc=((int(*)(void*,const char*,unsigned long,const char*,const char*)){addresses['luaL_loadbufferx']})(L,(const char*){scratch},{len(payload)},"MacGamingTrainer.Hades",(const char*)0);
              if(rc==0) rc=((int(*)(void*,int,int,int,int,void*)){addresses['lua_pcallk']})(L,0,1,0,0,(void*)0);
              unsigned long n=0;
              const char *s=((const char*(*)(void*,int,unsigned long*)){addresses['lua_tolstring']})(L,-1,&n);
              if(n>={capacity}){{n={capacity}-1;rc=100;}}
              if(s){{for(unsigned long i=0;i<n;++i)o[i]=s[i];}} else {{n=0;rc=101;}}
              o[n]=0;
              ((void(*)(void*,int)){addresses['lua_settop']})(L,top);
              rc;
            }})'''
            options = lldb.SBExpressionOptions()
            options.SetLanguage(lldb.eLanguageTypeC_plus_plus)
            options.SetTimeoutInMicroSeconds(2_000_000)
            options.SetIgnoreBreakpoints(True)
            options.SetUnwindOnError(True)
            options.SetStopOthers(True)
            options.SetTryAllThreads(False)
            result = thread.GetFrameAtIndex(0).EvaluateExpression(expression, options)
            if result.GetError().Fail():
                self.tainted = True
                raise failure('outcome_unknown', 'outcomeUnknown', str(result.GetError()))
            text = self.process.ReadCStringFromMemory(output, capacity, error)
            if error.Fail():
                self.tainted = True
                raise failure('outcome_unknown', 'outcomeUnknown', str(error))
            if result.GetValueAsSigned() != 0:
                if 'hades.error.restartRequired' in text:
                    raise failure('restart_required', 'restartRequired', text)
                for key in ('heroNotReady', 'invalidValue', 'staleTarget', 'staleTrait',
                            'unsupportedTrait', 'traitWeaponRequired', 'traitSlotOccupied'):
                    if 'hades.error.' + key in text:
                        raise failure('runtime_not_ready', key, text)
                if mutating:
                    self.tainted = True
                    raise failure('outcome_unknown', 'outcomeUnknown', text)
                raise failure('lua_error', 'debuggerCall', text)
            return json.loads(text)
        finally:
            primary_error = sys.exc_info()[1]
            if self.alive():
                try:
                    self._stop(time.monotonic() + 3)
                    self.target.DeleteAllBreakpoints()
                    self._restore_focus()
                    if scratch is not None:
                        self.process.DeallocateMemory(scratch)
                    self._resume(time.monotonic() + 3)
                except Exception as error:
                    self.tainted = True
                    detail = getattr(error, 'diagnostic', None) or str(error)
                    if primary_error is not None:
                        original = getattr(primary_error, 'diagnostic', None) or str(primary_error)
                        detail = original + '; cleanup: ' + detail
                    raise failure('outcome_unknown', 'outcomeUnknown', detail) from error

    def detach(self):
        if self.alive():
            self._stop(time.monotonic() + 3)
            self._restore_focus()
            self.target.DeleteAllBreakpoints()
            error = self.process.Detach()
            if error.Fail():
                raise failure('detach_failed', 'detachFailed', str(error))
        self.process = None
        self.pid = None
        self.addresses = {}
        self.focus_original = None

    def close(self):
        try:
            self.detach()
        finally:
            lldb.SBDebugger.Destroy(self.debugger)
