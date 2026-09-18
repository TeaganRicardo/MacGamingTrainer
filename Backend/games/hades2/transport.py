"""Supergiant/Hades II LLDB+Lua transport. This is a game-specific transport, not framework core."""
from pathlib import Path
import subprocess, sys, time, json, logging
sys.path.insert(0, subprocess.check_output(['xcrun','lldb','-P'], text=True).strip())
import lldb
from .config import GAME_SPEC

from core.adapter import AdapterError as TransportError

class Hades2LuaTransport:
    def __init__(self):
        lldb.SBDebugger.Initialize()
        self.debugger=lldb.SBDebugger.Create(); self.debugger.SetAsync(True)
        for setting,value in (('symbols.enable-external-lookup','false'), ('target.preload-symbols','false'), ('target.load-script-from-symbol-file','false'), ('symbols.load-on-demand','true')):
            result=lldb.SBCommandReturnObject()
            self.debugger.GetCommandInterpreter().HandleCommand('settings set '+setting+' '+value,result)
            if not result.Succeeded():raise TransportError('debugger_configuration',result.GetError())
        self.listener=self.debugger.GetListener()
        self.target=None; self.process=None; self.pid=None; self.addresses={}
        self.last_duration=0; self.last_attach_profile={}; self.focus_original=None; self.tainted=False
        manifest=json.loads(Path(__file__).with_name('symbols.json').read_text())
        self.symbols=manifest['symbols'];self.known_uuid=manifest['uuid'];self.runtime_uuid=None

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
        self.process=self.target.AttachToProcessWithID(self.listener,pid,error)
        profile['attachProcess']=time.monotonic()-phase
        if error.Fail():
            self.process=None
            profile['total']=time.monotonic()-started
            logging.info(
                'LLDBAttachProfile outcome=attach_denied total=%.3fs createTarget=%.3fs attachProcess=%.3fs',
                profile['total'],profile.get('createTarget',0.0),profile.get('attachProcess',0.0),
            )
            raise TransportError('attach_denied','连接被拒绝：'+str(error)+ '。退出游戏后使用“准备调试”，再重新启动。')

        self.pid=pid; self.addresses={}; self.tainted=False; self.focus_original=None
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

    def drain(self):
        event=lldb.SBEvent()
        while self.listener.GetNextEvent(event): pass

    def alive(self):
        self.drain()
        return self.process is not None and self.process.GetState() not in (lldb.eStateExited,lldb.eStateDetached,lldb.eStateInvalid)

    def wait_state(self, states, deadline):
        while time.monotonic()<deadline:
            self.drain()
            state=self.process.GetState()
            if state in states:return state
            if state in (lldb.eStateExited,lldb.eStateDetached):
                raise TransportError('disconnected','游戏进程已结束。')
            time.sleep(.005)
        raise TransportError('process_timeout','游戏进程状态切换超时。')

    def stop(self, deadline):
        while time.monotonic()<deadline:
            self.drain()
            if self.process.GetState()==lldb.eStateStopped:return
            error=self.process.Stop()
            self.drain()
            if self.process.GetState()==lldb.eStateStopped:return
            if error.Success():return self.wait_state((lldb.eStateStopped,),deadline)
            time.sleep(.01) # LLDB may still be completing an asynchronous resume.
        raise TransportError('stop_failed','无法在时限内暂停游戏。')

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

    def boundary(self, timeout=3):
        if self.tainted:raise TransportError('restart_required','上次调用结果不明，请重启游戏后重新连接。')
        if not self.alive():raise TransportError('disconnected','游戏已退出或连接已断开。')
        deadline=time.monotonic()+timeout
        self.stop(deadline)
        self.restore_focus() # Never overwrite an outstanding recovery value.
        error=lldb.SBError()
        focus=self.address('_ZN3sgg13ConfigOptions20RequireFocusToUpdateE')
        original=self.process.ReadMemory(focus,1,error)
        if error.Fail() or original not in (b'\x00',b'\x01'):raise TransportError('incompatible','后台运行标志无法验证。')
        self.focus_original=original
        if self.process.WriteMemory(focus,b'\x00',error)!=1 or error.Fail():raise TransportError('memory_error',str(error))
        bp=self.target.BreakpointCreateByAddress(self.address('lua_pcallk'))
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
                frame=th.GetFrameAtIndex(0);caller=th.GetFrameAtIndex(1).GetFunctionName() or ''
                L=frame.FindRegister('x0').GetValueAsUnsigned()
                err=lldb.SBError();root=self.process.ReadPointerFromMemory(self.address('_ZN3sgg13ScriptManager12LuaInterfaceE'),err)
                if th.GetName()=='MainThread' and caller=='sgg::World::Update(float)' and L and root==L and err.Success():return th,L
                self.resume(deadline,breakpoint_expected=True)
            raise TransportError('waiting','等待局内 Lua 调用超时。请进入存档并关闭暂停菜单后重试。')
        finally:
            self.target.BreakpointDelete(bp.GetID())

    def execute(self, source):
        started=time.monotonic(); scratch=None; stopped=False
        try:
            th,L=self.boundary();stopped=True
            payload=source.encode('utf-8')
            if len(payload)>262144:raise TransportError('invalid_request','功能代码过长。')
            cap=262144;size=len(payload)+1+cap
            err=lldb.SBError();scratch=self.process.AllocateMemory(size,lldb.ePermissionsReadable|lldb.ePermissionsWritable,err)
            if err.Fail():raise TransportError('memory_error',str(err))
            if self.process.WriteMemory(scratch,payload+b'\0',err)!=len(payload)+1 or err.Fail():raise TransportError('memory_error',str(err))
            out=scratch+len(payload)+1
            a=self.address
            # One expression; preserve the stack even on a Lua error. Copy result
            # before popping it, so host-side reading cannot race the Lua GC.
            expression=f'''({{
                void *L=(void*){L};
                int top=((int(*)(void*)){a('lua_gettop')})(L);
                int rc=((int(*)(void*,const char*,unsigned long,const char*,const char*)){a('luaL_loadbufferx')})(L,(const char*){scratch},{len(payload)},"MacGamingTrainer",(const char*)0);
                if(rc==0) rc=((int(*)(void*,int,int,int,int,void*)){a('lua_pcallk')})(L,0,1,0,0,(void*)0);
                unsigned long n=0;
                const char *s=((const char*(*)(void*,int,unsigned long*)){a('lua_tolstring')})(L,-1,&n);
                char *o=(char*){out};
                if(n>={cap}){{n={cap}-1;rc=100;}}
                if(s){{for(unsigned long i=0;i<n;++i)o[i]=s[i];}} else {{n=0;rc=101;}}
                o[n]=0;
                ((void(*)(void*,int)){a('lua_settop')})(L,top);
                rc;
            }})'''
            opts=lldb.SBExpressionOptions();opts.SetLanguage(lldb.eLanguageTypeC_plus_plus)
            opts.SetTimeoutInMicroSeconds(2000000);opts.SetIgnoreBreakpoints(True);opts.SetUnwindOnError(True)
            result=th.GetFrameAtIndex(0).EvaluateExpression(expression,opts)
            if result.GetError().Fail():
                self.tainted=True
                raise TransportError('outcome_unknown','游戏调用结果不明，未自动重试：'+str(result.GetError()))
            text=self.process.ReadCStringFromMemory(out,cap,err)
            if err.Fail():raise TransportError('outcome_unknown','无法读取操作结果；请检查游戏，不要重复资源操作。')
            if result.GetValueAsSigned()!=0:raise TransportError('lua_error',text or 'Lua 执行失败')
            return text
        finally:
            if self.process and self.alive():
                try:
                    self.stop(time.monotonic()+3)
                    self.restore_focus()
                    if scratch is not None:self.process.DeallocateMemory(scratch)
                    self.resume(time.monotonic()+3)
                except Exception:
                    self.tainted=True
                    raise
            self.last_duration=time.monotonic()-started

    def detach(self):
        if self.process and self.alive():
            self.stop(time.monotonic()+3)
            self.restore_focus()
            self.target.DeleteAllBreakpoints()
            error=self.process.Detach()
            if error.Fail():raise TransportError('detach_failed',str(error))
            self.drain()
        self.process=None;self.pid=None;self.addresses={};self.tainted=False
    def close(self):
        self.detach()
        if self.debugger:lldb.SBDebugger.Destroy(self.debugger);self.debugger=None


LuaTransport = Hades2LuaTransport
