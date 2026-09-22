from pathlib import Path
import json
import platform
import subprocess
import sys
import time
import zipfile

from core.log_paths import trainer_log_path
from core.protocol import PROTOCOL_VERSION, APP_BACKEND_VERSION
from . import preparation, localization
from .config import GAME_SPEC
from .schema import STAT_RULES


def build_diagnostics(adapter):
    checks=[]
    def add(name,ok,detail=''): checks.append({'name':name,'ok':bool(ok),'detail':str(detail)})
    if adapter.transport.alive():
        try: adapter.execute('status',{},read_only=True)
        except Exception: pass
    add('协议版本',True,f'host {PROTOCOL_VERSION} · module {adapter.module_protocol_version} · backend {APP_BACKEND_VERSION}')
    add('后端进程',True,sys.executable)
    add('Python',True,sys.version.split()[0]+' · '+platform.platform())
    add(GAME_SPEC.display_name+' 安装',preparation.GAME.exists(),preparation.GAME)
    symbols=Path(__file__).with_name('symbols.json')
    add('symbols.json',symbols.is_file(),symbols)
    add('存档目录',preparation.SAVES.exists(),preparation.SAVES)
    try:
        identity=preparation.compatibility(strict=False);add('游戏版本 / Build',True,f"{identity.get('version')} · Steam {identity.get('steam_build')}")
    except Exception as error:add('游戏版本 / Build',False,error)
    try:
        names=localization.official_display_names({'WeaponUpgrade'},'zh-CN');add('官方中文文本',bool(names.get('WeaponUpgrade')),names.get('WeaponUpgrade','未解析到 WeaponUpgrade'))
    except Exception as error:add('官方中文文本',False,error)
    try:
        result=subprocess.run(['/usr/bin/xcrun','--find','lldb'],capture_output=True,text=True,timeout=5);add('LLDB',result.returncode==0,result.stdout.strip() or result.stderr.strip())
    except Exception as error:add('LLDB',False,error)
    try:
        probe='import subprocess,sys; p=subprocess.check_output(["/usr/bin/xcrun","lldb","-P"], text=True).strip(); sys.path.insert(0,p); import lldb; print(lldb.SBDebugger)'
        result=subprocess.run(['/usr/bin/xcrun','python3','-c',probe],capture_output=True,text=True,timeout=8);add('LLDB Python',result.returncode==0,result.stdout.strip() or result.stderr.strip())
    except Exception as error:add('LLDB Python',False,error)

    state=adapter.state if isinstance(getattr(adapter,'state',None),dict) else {}
    add(GAME_SPEC.display_name+' 进程',bool(state.get('pid')),state.get('pid') or '未运行')
    add('Lua 连接',bool(state.get('connected')),state.get('status','unknown'))
    diag=state.get('runtimeDiagnostics',{}) if isinstance(state.get('runtimeDiagnostics'),dict) else {}
    add('Lua runtime revision',diag.get('revision') is not None,diag.get('revision','未连接'))
    add('当前场景',state.get('scene') in ('run','crossroads'),state.get('scene','unknown'))
    add('Hero ObjectId',diag.get('heroObjectId') is not None,diag.get('heroObjectId','不可用'))
    add('Run Count',state.get('runCount') is not None,state.get('runCount','不可用'))
    fs=state.get('featureSupport',{}) if isinstance(state.get('featureSupport'),dict) else {}
    for key in ('godMode','infiniteHealth','infiniteMana','instantCastCooldown','hexAlwaysReady','infiniteAmmo','autoMiniGames','gardenQoL','boonRarityEnabled','gameSpeed'):
        add('功能支持 · '+key,fs.get(key) is True,'支持' if fs.get(key) else '当前 runtime 不支持 / 未连接')
    ss=state.get('statSupport',{}) if isinstance(state.get('statSupport'),dict) else {}
    for key in (k for k in STAT_RULES if k!='grasp'):
        add('属性支持 · '+key,ss.get(key) is True,'支持' if ss.get(key) else '当前 runtime 不支持 / 未连接')
    cast=diag.get('castRuntime',{}) if isinstance(diag.get('castRuntime'),dict) else {}
    add('法阵 runtime',bool(fs.get('instantCastCooldown')),json.dumps(cast,ensure_ascii=False,default=str))
    hexdiag=diag.get('hexRuntime',{}) if isinstance(diag.get('hexRuntime'),dict) else {}
    add('巫咒 runtime',bool(fs.get('hexAlwaysReady')),json.dumps(hexdiag,ensure_ascii=False,default=str))
    return {
        'checks':checks,'passed':sum(1 for item in checks if item['ok']),'total':len(checks),
        'state':dict(state),'profiles':adapter.list_profiles(),
        'protocolVersion':PROTOCOL_VERSION,'moduleProtocolVersion':adapter.module_protocol_version,'backendVersion':APP_BACKEND_VERSION,
    }


def export_diagnostics(adapter):
    result=build_diagnostics(adapter)
    export_root=preparation.DATA/'diagnostics';export_root.mkdir(parents=True,exist_ok=True)
    stamp=time.strftime('%Y%m%d-%H%M%S')+f'-{time.time_ns()%1000000:06d}'
    zip_path=export_root/f'MacGamingTrainer-Diagnostics-{stamp}.zip'
    report={
        'generatedAt':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'protocolVersion':PROTOCOL_VERSION,
        'moduleProtocolVersion':adapter.module_protocol_version,'backendVersion':APP_BACKEND_VERSION,
        'python':sys.version,'platform':platform.platform(),'passed':result['passed'],'total':result['total'],
        'checks':result['checks'],'state':result['state'],
    }
    log_path=trainer_log_path(adapter.game_id);symbols=Path(__file__).with_name('symbols.json')
    with zipfile.ZipFile(zip_path,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('report.json',json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2,default=str)+'\n')
        if log_path.is_file():
            with log_path.open('rb') as stream:
                stream.seek(0,2);size=stream.tell();stream.seek(max(0,size-262144));archive.writestr('trainer.log.tail',stream.read())
        if symbols.is_file():archive.write(symbols,'symbols.json')
    return {'diagnosticBundle':str(zip_path),'passed':result['passed'],'total':result['total'],'checks':result['checks']}
