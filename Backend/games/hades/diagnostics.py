"""Read-only structured diagnostics report for Hades I."""

from datetime import datetime, timezone
import json
import platform
import sys

from core.adapter import AdapterError
from core.protocol import APP_BACKEND_VERSION, HOST_PROTOCOL_VERSION
from . import config


def _add_check(
    checks,
    check_id,
    name,
    ok,
    detail='',
    *,
    name_arguments=None,
    detail_arguments=None,
):
    row = {
        'id': str(check_id),
        'name': name,
        'ok': bool(ok),
        'detail': str(detail),
    }
    if name_arguments:
        row['nameArguments'] = [str(arg) for arg in name_arguments]
    if detail_arguments:
        row['detailArguments'] = [str(arg) for arg in detail_arguments]
    checks.append(row)


def _format_speed_detail(adapter):
    proj = adapter._game_speed_projection()
    error_key = proj.get('errorPresentation')
    if error_key:
        return error_key, proj.get('errorArguments') or None
    actual = proj.get('actual')
    desired = proj.get('desired', 1.0)
    if actual is not None:
        return 'hades.diagnostics.detail.speedObserved', [f'{desired:g}', f'{actual:g}']
    return 'hades.diagnostics.detail.speedDesired', [f'{desired:g}']


def build_diagnostics(adapter, state):
    manifest = json.loads((adapter.context.module_dir / 'module.json').read_text(encoding='utf-8'))
    checks = []

    located = None
    locate_error = None
    try:
        located = adapter.locate_process()
    except Exception as error:
        locate_error = error

    located_exe = None
    if located is not None and len(located) > 1 and located[1]:
        from pathlib import Path

        candidate = Path(located[1])
        if candidate.is_file():
            located_exe = candidate

    install = config.inspect_install(located_exe)

    # 1. protocol
    _add_check(
        checks,
        'protocol',
        'hades.diagnostics.protocol',
        True,
        'hades.diagnostics.detail.protocolVersion',
        detail_arguments=[HOST_PROTOCOL_VERSION, adapter.module_protocol_version, APP_BACKEND_VERSION],
    )
    # 2. backend
    _add_check(
        checks,
        'backend',
        'hades.diagnostics.backend',
        True,
        f'{sys.version.split()[0]} · {platform.platform()} · {sys.executable}',
    )
    # 3. install
    _add_check(
        checks,
        'install',
        'hades.diagnostics.check.install',
        install['installed'],
        str(install['gameApp']) if install['installed'] else 'hades.diagnostics.detail.notInstalled',
        name_arguments=[config.DISPLAY_NAME],
    )
    # 4. gameBuild
    if not install['installed']:
        _add_check(
            checks,
            'gameBuild',
            'hades.diagnostics.check.gameBuild',
            False,
            'hades.diagnostics.detail.notInstalled',
        )
    elif install['compatible']:
        _add_check(
            checks,
            'gameBuild',
            'hades.diagnostics.check.gameBuild',
            True,
            'hades.diagnostics.detail.gameBuild',
            detail_arguments=[
                install['version'] or '-',
                install['steamBuild'] or '-',
                install['uuid'] or '-',
            ],
        )
    else:
        _add_check(
            checks,
            'gameBuild',
            'hades.diagnostics.check.gameBuild',
            False,
            'hades.diagnostics.detail.gameBuildMismatch',
            detail_arguments=['; '.join(install['warnings'])],
        )
    # 5. symbols
    symbols_path = adapter.context.module_dir / 'symbols.json'
    symbol_detail = str(symbols_path)
    try:
        symbols_data = json.loads(symbols_path.read_text(encoding='utf-8'))
        symbols_map = symbols_data.get('symbols') if isinstance(symbols_data, dict) else None
        if isinstance(symbols_map, dict) and symbols_map:
            symbol_detail = 'hades.diagnostics.detail.symbolCount'
            _add_check(
                checks,
                'symbols',
                'hades.diagnostics.check.symbols',
                True,
                symbol_detail,
                detail_arguments=[len(symbols_map)],
            )
        else:
            _add_check(checks, 'symbols', 'hades.diagnostics.check.symbols', False, symbol_detail)
    except (OSError, ValueError) as error:
        _add_check(checks, 'symbols', 'hades.diagnostics.check.symbols', False, str(error))
    # 6. nativeMailbox
    mailbox_ok, mailbox_mode, mailbox_detail = config.probe_native_mailbox()
    _add_check(
        checks,
        'nativeMailbox',
        'hades.diagnostics.check.nativeMailbox',
        mailbox_ok,
        mailbox_detail,
        name_arguments=[mailbox_mode],
    )
    # 7. saves
    saves_path = config.saves_dir()
    if saves_path.is_dir():
        save_count = sum(1 for _ in saves_path.glob('Profile*.sav'))
        _add_check(
            checks,
            'saves',
            'hades.diagnostics.check.saves',
            True,
            'hades.diagnostics.detail.saveDirectory',
            detail_arguments=[save_count, str(saves_path)],
        )
    else:
        _add_check(checks, 'saves', 'hades.diagnostics.check.saves', False, str(saves_path))
    # 8. lldb
    lldb_ok, lldb_detail = config.probe_lldb()
    _add_check(checks, 'lldb', 'hades.diagnostics.check.lldb', lldb_ok, lldb_detail)
    # 9. lldbPython
    lldb_py_ok, lldb_py_detail = config.probe_lldb_python()
    _add_check(checks, 'lldbPython', 'hades.diagnostics.check.lldbPython', lldb_py_ok, lldb_py_detail)
    # 10. rosetta
    rosetta_ok, rosetta_detail = config.probe_rosetta()
    _add_check(checks, 'rosetta', 'hades.diagnostics.check.rosetta', rosetta_ok, rosetta_detail)
    # 11. process
    proc_pid = state.get('pid') or (located[0] if located is not None else None)
    if locate_error is not None and getattr(locate_error, 'code', None) == 'ambiguous_target':
        _add_check(
            checks,
            'process',
            'hades.diagnostics.check.process',
            False,
            getattr(locate_error, 'presentation', None) or str(locate_error),
            name_arguments=[config.DISPLAY_NAME],
        )
    elif proc_pid:
        _add_check(
            checks,
            'process',
            'hades.diagnostics.check.process',
            True,
            'hades.diagnostics.detail.processRunning',
            name_arguments=[config.DISPLAY_NAME],
            detail_arguments=[proc_pid, str(located[1]) if located is not None else config.EXECUTABLE_SUFFIX],
        )
    else:
        _add_check(
            checks,
            'process',
            'hades.diagnostics.check.process',
            False,
            'hades.diagnostics.detail.notRunning',
            name_arguments=[config.DISPLAY_NAME],
        )
    # 12. connection (preserve legacy name)
    connected = bool(state.get('connected'))
    _add_check(
        checks,
        'connection',
        'hades.diagnostics.connection',
        connected,
        'hades.diagnostics.detail.connectedPid' if connected else 'hades.diagnostics.detail.disconnected',
        detail_arguments=[state.get('pid') or '-', mailbox_mode] if connected else None,
    )
    # 13. luaRevision
    revision = state.get('runtimeRevision')
    _add_check(
        checks,
        'luaRevision',
        'hades.diagnostics.check.luaRevision',
        bool(revision),
        str(revision)[:12] if revision else 'hades.diagnostics.detail.disconnected',
    )
    # 14. currentScene
    scene = state.get('scene') or 'unknown'
    if scene not in ('house', 'courtyard', 'run', 'loading', 'main_menu', 'unknown'):
        scene = 'unknown'
    room_name = state.get('roomName')
    scene_ok = connected and scene in ('house', 'courtyard', 'run')
    if room_name:
        _add_check(
            checks,
            'currentScene',
            'hades.diagnostics.check.currentScene',
            scene_ok,
            'hades.diagnostics.detail.sceneWithRoom',
            detail_arguments=[f'hades.scene.{scene}', room_name],
        )
    else:
        _add_check(
            checks,
            'currentScene',
            'hades.diagnostics.check.currentScene',
            scene_ok,
            f'hades.scene.{scene}',
        )
    # 15. hero (preserve legacy name)
    hero_ready = bool(state.get('heroReady'))
    hero_id = str((state.get('target') or {}).get('heroId', '') or '')
    _add_check(
        checks,
        'hero',
        'hades.diagnostics.hero',
        hero_ready,
        hero_id if (hero_ready and hero_id) else 'hades.diagnostics.detail.notAvailable',
    )
    # 16. speed (preserve legacy name, structured localized summary — zero json.dumps)
    speed_detail, speed_args = _format_speed_detail(adapter)
    _add_check(
        checks,
        'speed',
        'hades.diagnostics.speed',
        adapter._game_speed_actual is not None and adapter._game_speed_error is None,
        speed_detail,
        detail_arguments=speed_args,
    )
    # 17. preferences (safe even if unreadable or newer-schema)
    desired = None
    pref_error = getattr(adapter, '_preferences_error', None)
    try:
        desired = adapter.preferences.load()
        pref_error = None
    except AdapterError as error:
        pref_error = error
    if pref_error is None:
        _add_check(checks, 'preferences', 'hades.diagnostics.check.preferences', True, str(adapter.preferences.path))
    else:
        _add_check(
            checks,
            'preferences',
            'hades.diagnostics.check.preferences',
            False,
            pref_error.presentation or str(pref_error),
        )
    # 18. profiles
    try:
        profile_rows = adapter.profiles.list()
        _add_check(
            checks,
            'profiles',
            'hades.diagnostics.check.profiles',
            True,
            'hades.diagnostics.detail.profileCount',
            detail_arguments=[len(profile_rows)],
        )
    except Exception as error:
        _add_check(
            checks,
            'profiles',
            'hades.diagnostics.check.profiles',
            False,
            getattr(error, 'presentation', None) or str(error),
        )
    # 19. recovery
    recovery = state.get('recovery') if 'recovery' in state else adapter._describe_recovery()
    if recovery is None:
        _add_check(
            checks,
            'recovery',
            'hades.diagnostics.check.recovery',
            True,
            'hades.diagnostics.detail.recoveryClean',
        )
    elif recovery.get('outcome') == 'unavailable':
        _add_check(
            checks,
            'recovery',
            'hades.diagnostics.check.recovery',
            False,
            recovery.get('presentation') or 'hades.error.recoveryFailed',
        )
    else:
        _add_check(
            checks,
            'recovery',
            'hades.diagnostics.check.recovery',
            False,
            'hades.diagnostics.detail.recoveryPending',
            detail_arguments=[
                recovery.get('outcome') or 'unknown',
                recovery.get('method') or '-',
                recovery.get('pid') or '-',
            ],
        )

    return {
        'generatedAt': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'gameID': 'hades',
        'supportedBuild': manifest['supportedBuild'],
        'checks': checks,
        'passed': sum(1 for item in checks if item['ok']),
        'total': len(checks),
        'protocolVersion': HOST_PROTOCOL_VERSION,
        'moduleProtocolVersion': adapter.module_protocol_version,
        'backendVersion': APP_BACKEND_VERSION,
        'state': state,
        'desired': desired,
    }
