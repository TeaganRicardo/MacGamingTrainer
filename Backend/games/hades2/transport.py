"""Supergiant/Hades II LLDB+Lua transport. This is a game-specific transport, not framework core."""
import json
import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, subprocess.check_output(['/usr/bin/xcrun','lldb','-P'], text=True, shell=False).strip())
import lldb
from core.operation_profile import profiled
from core.adapter import AdapterError as TransportError

from .config import GAME_SPEC, LUA_TRANSPORT_RESULT_LIMIT_BYTES, LUA_TRANSPORT_SOURCE_LIMIT_BYTES
from .native_effect_query import prepare_native_query
from .mailbox import Hades2CommandMailbox
from .native_mailbox import prepare_command_mailbox, install_command_mailbox


class Hades2LuaTransport:
    def __init__(self):
        self.mailbox_mode = os.environ.get('MGT_HADES2_TRANSPORT', 'mailbox')
        if self.mailbox_mode not in ('mailbox', 'lldb'):
            raise ValueError('MGT_HADES2_TRANSPORT must be mailbox or lldb')
        self._mailbox = None
        self.native_mailbox_library = None
        self.last_mailbox_profile = {}
        lldb.SBDebugger.Initialize()
        self.debugger=lldb.SBDebugger.Create(); self.debugger.SetAsync(True)
        for setting,value in (('symbols.enable-external-lookup','false'), ('target.preload-symbols','false'), ('target.load-script-from-symbol-file','false'), ('symbols.load-on-demand','true')):
            result=lldb.SBCommandReturnObject()
            self.debugger.GetCommandInterpreter().HandleCommand('settings set '+setting+' '+value,result)
            if not result.Succeeded():raise TransportError('debugger_configuration',result.GetError())
        self.listener=self.debugger.GetListener()
        self.target=None; self.process=None; self.pid=None; self.addresses={}; self.native_runtime_installer=None
        self.last_duration=0; self.last_expression_duration=0; self.last_attach_profile={}; self.focus_original=None; self.tainted=False
        manifest=json.loads(Path(__file__).with_name('symbols.json').read_text())
        self.symbols=manifest['symbols'];self.known_uuid=manifest['uuid'];self.runtime_uuid=None

    @property
    def tainted(self):
        mailbox = getattr(self, '_mailbox', None)
        return getattr(self, '_tainted', False) or (mailbox is not None and mailbox.tainted)

    @tainted.setter
    def tainted(self, value):
        self._tainted = bool(value)
        if value and getattr(self, '_mailbox', None) is not None:
            self._mailbox.poison()

    def attach(self,pid):
        if self.process:
            if self.pid==pid and self.alive():
                self.last_attach_profile={'reused':True,'total':0.0}
                return
            self.detach()
        started=time.monotonic();profile={}
        self.last_attach_profile=profile

        phase=time.monotonic()
        self.target=self.debugger.CreateTarget('') # Attach discovers the runtime image once; avoid a duplicate file target.
        profile['createTarget']=time.monotonic()-phase

        error=lldb.SBError()
        phase=time.monotonic()
        try:
            self.process=self.target.AttachToProcessWithID(self.listener,pid,error)
        finally:
            profile['attachProcess']=time.monotonic()-phase
        if error.Fail():
            self.process=None
            profile['total']=time.monotonic()-started
            logging.info(
                'LLDBAttachProfile outcome=attach_denied total=%.3fs createTarget=%.3fs attachProcess=%.3fs',
                profile['total'],profile.get('createTarget',0.0),profile.get('attachProcess',0.0),
            )
            raise TransportError('attach_denied','连接被拒绝：'+str(error)+ '。退出游戏后使用“准备调试”，再重新启动。')

        self.pid=pid; self.addresses={}; self.tainted=False; self.focus_original=None; self.native_runtime_installer=None
        try:
            phase=time.monotonic()
            try:
                self.runtime_uuid=self.target.GetModuleAtIndex(0).GetUUIDString()
                triple = self.target.GetTriple() or ''
                required_arch = GAME_SPEC.minimum_architecture
                arch_ok = True
                if required_arch == 'arm64':
                    arch_ok = triple.startswith(('arm64-', 'aarch64-'))
                elif required_arch:
                    arch_ok = triple.startswith(required_arch + '-')
                if not self.runtime_uuid or not arch_ok:
                    requirement = required_arch or '受支持架构'
                    raise TransportError('incompatible',f'{GAME_SPEC.display_name} 适配器需要 {requirement} 原生游戏。')
            finally:
                profile['identity']=time.monotonic()-phase

            phase=time.monotonic()
            try:
                for name in self.symbols:
                    self.address(name)
            finally:
                profile['symbols']=time.monotonic()-phase
            phase=time.monotonic()
            try:
                self.native_runtime_installer=prepare_native_query(self,lldb)
            finally:
                profile['nativeQuery']=time.monotonic()-phase
            if self.mailbox_mode == 'mailbox':
                phase=time.monotonic()
                try:
                    self.native_mailbox_library=prepare_command_mailbox(self,lldb)
                finally:
                    profile['nativeMailbox']=time.monotonic()-phase
        except Exception as exc:
            profile['total']=time.monotonic()-started
            logging.info(
                'LLDBAttachProfile outcome=%s total=%.3fs createTarget=%.3fs attachProcess=%.3fs identity=%.3fs symbols=%.3fs',
                getattr(exc,'code',type(exc).__name__),profile['total'],profile.get('createTarget',0.0),
                profile.get('attachProcess',0.0),profile.get('identity',0.0),profile.get('symbols',0.0),
            )
            self.detach()
            raise

        phase=time.monotonic()
        try:
            self.resume(time.monotonic()+3)
        except Exception as exc:
            profile['resume']=time.monotonic()-phase
            profile['total']=time.monotonic()-started
            logging.info(
                'LLDBAttachProfile outcome=%s total=%.3fs createTarget=%.3fs attachProcess=%.3fs identity=%.3fs symbols=%.3fs resume=%.3fs',
                getattr(exc,'code',type(exc).__name__),profile['total'],profile.get('createTarget',0.0),
                profile.get('attachProcess',0.0),profile.get('identity',0.0),profile.get('symbols',0.0),profile.get('resume',0.0),
            )
            raise
        profile['resume']=time.monotonic()-phase
        profile['total']=time.monotonic()-started
        logging.info(
            'LLDBAttachProfile outcome=ok total=%.3fs createTarget=%.3fs attachProcess=%.3fs identity=%.3fs symbols=%.3fs resume=%.3fs',
            profile['total'],profile.get('createTarget',0.0),profile.get('attachProcess',0.0),
            profile.get('identity',0.0),profile.get('symbols',0.0),profile.get('resume',0.0),
        )

    def address(self,name):
        if name in self.addresses:return self.addresses[name]
        if name not in self.symbols:raise TransportError('incompatible','缺少符号：'+name)
        if self.runtime_uuid!=self.known_uuid:
            # A new build may move every address. Resolve only symbols owned by
            # its live main image; never reuse the old build's RVAs or prefixes.
            module=self.target.GetModuleAtIndex(0)
            matches=module.FindSymbols(name,lldb.eSymbolTypeAny)
            addresses=set()
            for i in range(matches.GetSize()):
                symbol=matches.GetContextAtIndex(i).GetSymbol()
                address=symbol.GetStartAddress().GetLoadAddress(self.target)
                if symbol.IsValid() and address not in (0,lldb.LLDB_INVALID_ADDRESS):addresses.add(address)
            if len(addresses)!=1:
                raise TransportError('incompatible','新版本关键符号无法唯一定位：'+name)
            address=addresses.pop()
            error=lldb.SBError()
            if len(self.process.ReadMemory(address,1,error) or b'')!=1 or error.Fail():
                raise TransportError('incompatible','新版本关键符号不可读：'+name)
            self.addresses[name]=address;return address
        base=self.target.GetModuleAtIndex(0).GetObjectFileHeaderAddress().GetLoadAddress(self.target)
        if base==lldb.LLDB_INVALID_ADDRESS:raise TransportError('incompatible','无法定位游戏镜像。')
        entry=self.symbols[name];address=base+entry['rva']
        if 'prefix' in entry:
            error=lldb.SBError();expected=bytes.fromhex(entry['prefix'])
            actual=self.process.ReadMemory(address,len(expected),error)
            if error.Fail() or actual!=expected:raise TransportError('incompatible','运行中的游戏函数校验失败：'+name)
        self.addresses[name]=address;return address

    @profiled("debugger.drain")
    def drain(self):
        event=lldb.SBEvent()
        while self.listener.GetNextEvent(event): pass

    def alive(self):
        self.drain()
        return self.process is not None and self.process.GetState() not in (lldb.eStateExited,lldb.eStateDetached,lldb.eStateInvalid)

    def wait_state(self, states, deadline, *, phase='transport.stop', primary_error_code=None):
        last_observed_state=None
        while time.monotonic()<deadline:
            self.drain()
            state=self.process.GetState()
            last_observed_state=state
            if state in states:return state
            if state in (lldb.eStateExited,lldb.eStateDetached):
                raise TransportError('disconnected','游戏进程已结束。')
            time.sleep(.005)
        observation={'phase':phase,'expectedStates':list(states),'lastObservedState':last_observed_state}
        if primary_error_code is not None:observation['primary_error_code']=primary_error_code
        raise TransportError('process_timeout','游戏进程状态切换超时。',diagnostic=json.dumps(observation,separators=(',',':')))

    @profiled("debugger.stop")
    def stop(self, deadline, *, phase='transport.stop', primary_error_code=None):
        self.drain()
        state=self.process.GetState()
        if state==lldb.eStateStopped:return
        if state in (lldb.eStateInvalid,lldb.eStateExited,lldb.eStateDetached):
            raise TransportError('disconnected','游戏进程已结束。')
        if time.monotonic()>=deadline:
            raise TransportError('stop_failed','无法在时限内暂停游戏。')
        # LLDB owns the stop request and its process-state event. An asynchronous
        # request is not completion: observe the stop within the original deadline.
        self.process.SendAsyncInterrupt()
        return self.wait_state((lldb.eStateStopped,),deadline,phase=phase,primary_error_code=primary_error_code)

    @profiled("debugger.resume")
    def resume(self, deadline, breakpoint_expected=False):
        self.drain()
        if self.process.GetState()==lldb.eStateRunning:return
        previous_stop=self.process.GetStopID()
        error=self.process.Continue()
        if error.Fail():raise TransportError('resume_failed','无法恢复游戏运行：'+str(error))
        while time.monotonic()<deadline:
            self.drain()
            state=self.process.GetState()
            if state==lldb.eStateRunning:return
            if breakpoint_expected and state==lldb.eStateStopped and self.process.GetStopID()>previous_stop:return
            if state in (lldb.eStateExited,lldb.eStateDetached):raise TransportError('disconnected','游戏进程已结束。')
            time.sleep(.005)
        raise TransportError('resume_failed','游戏未能恢复运行。')

    def restore_focus(self):
        if self.focus_original is None:return
        if self.process.GetState()!=lldb.eStateStopped:
            raise TransportError('restore_failed','后台暂停标志尚未恢复，请保持连接重试断开。')
        address=self.address('_ZN3sgg13ConfigOptions20RequireFocusToUpdateE')
        error=lldb.SBError()
        count=self.process.WriteMemory(address,self.focus_original,error)
        if error.Fail() or count!=1:raise TransportError('restore_failed','后台暂停标志恢复失败：'+str(error))
        actual=self.process.ReadMemory(address,1,error)
        if error.Fail() or actual!=self.focus_original:raise TransportError('restore_failed','后台暂停标志恢复校验失败。')
        self.focus_original=None

    @profiled("debugger.boundary")
    def boundary(self, timeout=3, *, entry_address=None):
        if self.tainted:raise TransportError('restart_required','上次调用结果不明，请重启游戏后重新连接。')
        if not self.alive():raise TransportError('disconnected','游戏已退出或连接已断开。')
        deadline=time.monotonic()+timeout
        self.stop(deadline,phase='boundary.initial_stop')
        self.restore_focus() # Never overwrite an outstanding recovery value.
        error=lldb.SBError()
        focus=self.address('_ZN3sgg13ConfigOptions20RequireFocusToUpdateE')
        original=self.process.ReadMemory(focus,1,error)
        if error.Fail() or original not in (b'\x00',b'\x01'):raise TransportError('incompatible','后台运行标志无法验证。')
        self.focus_original=original
        if self.process.WriteMemory(focus,b'\x00',error)!=1 or error.Fail():raise TransportError('memory_error',str(error))
        bp=self.target.BreakpointCreateByAddress(
            entry_address if entry_address is not None else self.address('_ZN3sgg5World6UpdateEf'))
        leased=False
        try:
            self.resume(deadline,breakpoint_expected=True)
            while time.monotonic()<deadline:
                self.drain()
                state=self.process.GetState()
                if state in (lldb.eStateExited,lldb.eStateDetached):raise TransportError('disconnected','游戏进程已退出。')
                if state!=lldb.eStateStopped:
                    time.sleep(.005);continue
                matching=[th for th in self.process if th.GetStopReason()==lldb.eStopReasonBreakpoint and th.GetStopReasonDataAtIndex(0)==bp.GetID()]
                if not matching:raise TransportError('unexpected_stop','游戏发生非预期停顿，已停止当前操作。')
                th=matching[0]
                err=lldb.SBError()
                L=self.process.ReadPointerFromMemory(self.address('_ZN3sgg13ScriptManager12LuaInterfaceE'),err)
                if th.GetName()=='MainThread' and L and err.Success():
                    # Preserve the stop-reason breakpoint identity through LLDB
                    # expression evaluation. Disable it so the expression cannot
                    # hit the synchronization point; execute() deletes it after
                    # evaluation/unwind has finished.
                    bp.SetEnabled(False)
                    leased=True
                    return th,L,bp
                self.resume(deadline,breakpoint_expected=True)
            raise TransportError('waiting',
                '等待游戏主线程就绪超时，请在游戏就绪后重试。' if entry_address is not None
                else '等待游戏世界更新超时。请进入存档并关闭暂停菜单后重试。')
        finally:
            if not leased:self.target.BreakpointDelete(bp.GetID())

    def execute(self, source, *, expression_timeout_seconds=2.0):
        if getattr(self, 'mailbox_mode', 'lldb') == 'mailbox':
            return self._execute_mailbox(source, expression_timeout_seconds=expression_timeout_seconds)
        return self._execute_lldb(source, expression_timeout_seconds=expression_timeout_seconds)

    def _execute_mailbox(self, source, *, expression_timeout_seconds=2.0):
        started=time.monotonic()
        self.last_expression_duration=0
        self.last_mailbox_profile={}
        try:
            if self.tainted:
                raise TransportError('restart_required','hades2.error.restartRequired')
            if not self.alive():
                raise TransportError('disconnected','hades2.error.notAttached')
            if self._mailbox is None:
                library=self.native_mailbox_library
                if library is None:
                    raise TransportError('incompatible','hades2.error.commandConnectionUnavailable')
                try:
                    mailbox=Hades2CommandMailbox(library.path,self.pid,alive=self.alive)
                except (OSError,ValueError) as error:
                    raise TransportError('incompatible','hades2.error.commandConnectionUnavailable',diagnostic=str(error)) from error
                self._mailbox=mailbox
                try:
                    install_command_mailbox(self,lldb,mailbox,library)
                except BaseException:
                    mailbox.close()
                    self._mailbox=None
                    raise
            try:
                return self._mailbox.execute(source,timeout_seconds=expression_timeout_seconds)
            except TransportError as error:
                if self._mailbox.tainted:
                    self.tainted=True
                if error.code == 'resident_generation_missing':
                    # The native consumer proved this source never executed.
                    # The resident owner decides whether a later status may
                    # bootstrap; this request is never replayed here.
                    self._mailbox.close()
                    self._mailbox=None
                raise
        finally:
            self.last_duration=time.monotonic()-started
            if self._mailbox is not None:
                self.last_mailbox_profile=dict(self._mailbox.last_profile)

    def acknowledge_result(self):
        if self._mailbox is not None:
            try:
                self._mailbox.acknowledge()
            except BaseException:
                self.tainted=True
                raise

    @profiled("debugger.execute")
    def _execute_lldb(self, source, *, expression_timeout_seconds=2.0):
        started=time.monotonic(); scratch=None; bp=None; self.last_expression_duration=0; primary_error_code=None
        try:
            th,L,bp=self.boundary()
            payload=source.encode('utf-8')
            if len(payload)>LUA_TRANSPORT_SOURCE_LIMIT_BYTES:raise TransportError('invalid_request','功能代码过长。')
            library=getattr(self,'native_runtime_installer',None)
            cap=LUA_TRANSPORT_RESULT_LIMIT_BYTES;size=len(payload)+1+cap
            err=lldb.SBError();scratch=self.process.AllocateMemory(size,lldb.ePermissionsReadable|lldb.ePermissionsWritable,err)
            if err.Fail():raise TransportError('memory_error',str(err))
            if self.process.WriteMemory(scratch,payload+b'\0',err)!=len(payload)+1 or err.Fail():raise TransportError('memory_error',str(err))
            out=scratch+len(payload)+1
            a=self.address
            install=f'((int(*)(void*,unsigned long,char*,unsigned long)){library.installer})(L,{library.target_header_base},o,{cap})' if library is not None else '0'
            # One expression; preserve the stack even on a Lua error. Copy result
            # before popping it, so host-side reading cannot race the Lua GC.
            expression=f'''({{
                void *L=(void*){L};
                char *o=(char*){out};
                o[0]=0;
                int top=((int(*)(void*)){a('lua_gettop')})(L);
                int rc={install};
                if(rc==0) rc=((int(*)(void*,const char*,unsigned long,const char*,const char*)){a('luaL_loadbufferx')})(L,(const char*){scratch},{len(payload)},"MacGamingTrainer",(const char*)0);
                if(rc==0) rc=((int(*)(void*,int,int,int,int,void*)){a('lua_pcallk')})(L,0,1,0,0,(void*)0);
                if(rc>=0){{
                    unsigned long n=0;
                    const char *s=((const char*(*)(void*,int,unsigned long*)){a('lua_tolstring')})(L,-1,&n);
                    if(n>={cap}){{n={cap}-1;rc=100;}}
                    if(s){{for(unsigned long i=0;i<n;++i)o[i]=s[i];}} else {{n=0;rc=101;}}
                    o[n]=0;
                }}
                ((void(*)(void*,int)){a('lua_settop')})(L,top);
                rc;
            }})'''
            if type(expression_timeout_seconds) not in (int,float) or not 0 < expression_timeout_seconds <= 30:
                raise ValueError('expression_timeout_seconds must be within (0, 30].')
            opts=lldb.SBExpressionOptions();opts.SetLanguage(lldb.eLanguageTypeC_plus_plus)
            opts.SetTimeoutInMicroSeconds(int(expression_timeout_seconds*1000000));opts.SetIgnoreBreakpoints(True);opts.SetUnwindOnError(True)
            opts.SetStopOthers(True);opts.SetTryAllThreads(False)
            expression_started=time.monotonic()
            result=th.GetFrameAtIndex(0).EvaluateExpression(expression,opts)
            self.last_expression_duration=time.monotonic()-expression_started
            if result.GetError().Fail():
                self.tainted=True
                detail=str(result.GetError())
                if self.last_expression_duration >= expression_timeout_seconds:
                    detail=(
                        f'LLDB expression exceeded {expression_timeout_seconds:g}s budget '
                        f'after {self.last_expression_duration:.3f}s; '+detail
                    )
                raise TransportError('outcome_unknown','游戏调用结果不明，未自动重试：'+detail)
            text=self.process.ReadCStringFromMemory(out,cap,err)
            if err.Fail():
                self.tainted=True
                raise TransportError('outcome_unknown','无法读取操作结果；请检查游戏，不要重复资源操作。')
            status=result.GetValueAsSigned()
            if status<0:
                raise TransportError(
                    'incompatible','hades2.error.nativeQueryUnavailable',
                    diagnostic=f'Native query registration status={status}: '+text,
                )
            if status!=0:
                marker='MGT_OUTCOME_UNKNOWN:'
                if marker in text:
                    self.tainted=True
                    message=text.split(marker,1)[1].strip()
                    raise TransportError('outcome_unknown',message or '游戏调用结果不明，未自动重试。')
                raise TransportError('lua_error',text or 'Lua 执行失败')
            return text
        except Exception as exc:
            primary_error_code=getattr(exc,'code',None)
            raise
        finally:
            if bp is not None and self.target:
                self.target.BreakpointDelete(bp.GetID())
            if self.process and self.alive():
                try:
                    self.stop(time.monotonic()+3,phase='execute.cleanup_stop',primary_error_code=primary_error_code)
                    self.restore_focus()
                    if scratch is not None:self.process.DeallocateMemory(scratch)
                    self.resume(time.monotonic()+3)
                except Exception:
                    self.tainted=True
                    raise
            self.last_duration=time.monotonic()-started

    def detach(self):
        detached_pid=None
        mailbox=getattr(self,'_mailbox',None)
        if mailbox is not None:
            mailbox.close()
            self._mailbox=None
        if self.process and self.alive():
            self.stop(time.monotonic()+3,phase='detach.stop')
            self.restore_focus()
            self.target.DeleteAllBreakpoints()
            error=self.process.Detach()
            if error.Fail():raise TransportError('detach_failed',str(error))
            detached_pid=self.pid
            self.drain()
        self.process=None;self.pid=None;self.addresses={};self.tainted=False;self.native_runtime_installer=None;self.native_mailbox_library=None
        if detached_pid is not None:
            # LLDB has released the target, but macOS may retain its BSD stop
            # signal. Complete the process handoff after debugger ownership ends.
            # The released attachment stays cleared even if OS resume fails.
            try:
                os.kill(detached_pid,signal.SIGCONT)
            except ProcessLookupError:
                pass # The target exited after release; no attachment remains.
            except OSError as exc:
                raise TransportError('resume_failed','hades2.error.resumeFailed',
                                     diagnostic=str(exc),arguments=[str(exc)]) from exc
    def close(self):
        self.detach()
        if self.debugger:lldb.SBDebugger.Destroy(self.debugger);self.debugger=None


LuaTransport = Hades2LuaTransport
