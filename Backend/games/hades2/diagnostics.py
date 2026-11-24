import json
import platform
import sys
from pathlib import Path

from core.protocol import APP_BACKEND_VERSION, HOST_PROTOCOL_VERSION
from core.target_probe import bounded_run

from . import localization, preparation, schema
from .config import DISPLAY_NAME
from .operation_budgets import LLDB_DISCOVERY_TIMEOUT_SECONDS, LLDB_PYTHON_TIMEOUT_SECONDS
from .schema import STAT_RULES

_FEATURE_LABEL_KEYS = {
    'invincibility': 'hades2.feature.invincibility',
    'infiniteHealth': 'hades2.feature.infiniteHealth',
    'infiniteMana': 'hades2.feature.infiniteMana',
    'infiniteMoney': 'hades2.feature.infiniteMoney',
    'infiniteRerolls': 'hades2.feature.infiniteRerolls',
    'damageMultiplier': 'hades2.feature.damageMultiplier',
    'instantCastCooldown': 'hades2.feature.instantCastCooldown',
    'hexAlwaysReady': 'hades2.feature.hexAlwaysReady',
    'infiniteAmmo': 'hades2.feature.infiniteAmmo',
    'autoMiniGames': 'hades2.feature.autoMiniGames',
    'boonRarityEnabled': 'hades2.rarity.minimum',
    'forceEnableRerolls': 'hades2.feature.forceEnableRerolls',
    'moneyMultiplierEnabled': 'hades2.feature.moneyMultiplier',
    'resourceMultiplierEnabled': 'hades2.feature.resourceMultiplier',
    'gameSpeed': 'hades2.gameSpeed.title',
}

_STAT_LABEL_KEYS = {
    'dodge': 'hades2.stat.dodge',
    'crit': 'hades2.stat.crit',
    'chargeSpeed': 'hades2.stat.chargeSpeed',
    'moveSpeed': 'hades2.stat.moveSpeed',
    'sprintSpeed': 'hades2.stat.sprintSpeed',
    'dashSpeed': 'hades2.stat.dashSpeed',
    'attackSpeed': 'hades2.stat.attackSpeed',
    'manaRegen': 'hades2.stat.manaRegen',
    'enemyDamage': 'hades2.stat.enemyDamage',
    'enemyHealth': 'hades2.stat.enemyHealth',
}


def _feature_label_key(key):
    return _FEATURE_LABEL_KEYS.get(key, key)


def build_diagnostics(adapter):
    checks = []

    def add(
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

    state = {}
    last_known_state = adapter.state if isinstance(getattr(adapter, 'state', None), dict) else {}
    runtime_observation_available = False
    try:
        if adapter.runtime.alive():
            refreshed = adapter.observe_runtime()
            if not isinstance(refreshed, dict):
                raise RuntimeError('status refresh returned no runtime state')
            state = refreshed
            runtime_observation_available = True
            add(
                'runtimeRefresh',
                'hades2.diagnostics.check.runtimeRefresh',
                True,
                'hades2.diagnostics.detail.liveRuntime',
            )
        else:
            add(
                'runtimeRefresh',
                'hades2.diagnostics.check.runtimeRefresh',
                False,
                'hades2.diagnostics.detail.residentDisconnected',
            )
    except Exception as error:
        add('runtimeRefresh', 'hades2.diagnostics.check.runtimeRefresh', False, str(error))

    add(
        'protocolVersion',
        'hades2.diagnostics.check.protocolVersion',
        True,
        'hades2.diagnostics.detail.protocolVersion',
        detail_arguments=[HOST_PROTOCOL_VERSION, adapter.module_protocol_version, APP_BACKEND_VERSION],
    )
    add('backendProcess', 'hades2.diagnostics.check.backendProcess', True, sys.executable)
    add('python', 'hades2.diagnostics.check.python', True, f'{sys.version.split()[0]} · {platform.platform()}')

    game_dir = adapter.install_path() if callable(getattr(adapter, 'install_path', None)) else preparation.resolve_paths()[0]
    identity = None
    identity_error = None
    try:
        identity = preparation.compatibility(strict=False)
        if isinstance(identity.get('game'), str) and identity['game']:
            game_dir = Path(identity['game'])
    except Exception as error:
        identity_error = error
    add(
        'install',
        'hades2.diagnostics.check.install',
        game_dir.exists(),
        game_dir,
        name_arguments=[DISPLAY_NAME],
    )
    symbols = Path(__file__).with_name('symbols.json')
    add('symbols', 'hades2.diagnostics.check.symbols', symbols.is_file(), symbols)
    add('saves', 'hades2.diagnostics.check.saves', preparation.SAVES.exists(), preparation.SAVES)
    if identity is not None:
        warnings = identity.get('warnings') if isinstance(identity.get('warnings'), list) else []
        detail = f"{identity.get('version')} · Steam {identity.get('steam_build')}"
        if warnings:
            detail += ' · ' + '; '.join(map(str, warnings))
        add('gameBuild', 'hades2.diagnostics.check.gameBuild', identity.get('compatible') is True, detail)
    else:
        add(
            'gameBuild',
            'hades2.diagnostics.check.gameBuild',
            False,
            getattr(identity_error, 'presentation', None) or identity_error,
            detail_arguments=getattr(identity_error, 'arguments', None),
        )
    try:
        names = localization.official_display_names({'WeaponUpgrade'}, 'zh-CN', game_path=game_dir)
        resolved = names.get('WeaponUpgrade')
        add(
            'officialText',
            'hades2.diagnostics.check.officialText',
            bool(resolved),
            resolved or 'hades2.diagnostics.detail.missingWeaponUpgrade',
        )
    except Exception as error:
        add('officialText', 'hades2.diagnostics.check.officialText', False, error)
    try:
        result = bounded_run(['/usr/bin/xcrun', '--find', 'lldb'], LLDB_DISCOVERY_TIMEOUT_SECONDS, text=True)
        add(
            'lldb',
            'hades2.diagnostics.check.lldb',
            result.returncode == 0,
            result.stdout.strip() or result.stderr.strip(),
        )
    except Exception as error:
        add('lldb', 'hades2.diagnostics.check.lldb', False, error)
    try:
        probe = (
            'import subprocess,sys; p=subprocess.check_output(["/usr/bin/xcrun","lldb","-P"], text=True).strip(); '
            'sys.path.insert(0,p); import lldb; print(lldb.SBDebugger)'
        )
        result = bounded_run(['/usr/bin/xcrun', 'python3', '-c', probe], LLDB_PYTHON_TIMEOUT_SECONDS, text=True)
        add(
            'lldbPython',
            'hades2.diagnostics.check.lldbPython',
            result.returncode == 0,
            result.stdout.strip() or result.stderr.strip(),
        )
    except Exception as error:
        add('lldbPython', 'hades2.diagnostics.check.lldbPython', False, error)

    if runtime_observation_available:
        pid = state.get('pid')
        add(
            'process',
            'hades2.diagnostics.check.process',
            bool(pid),
            pid if pid else 'hades2.diagnostics.detail.notRunning',
            name_arguments=[DISPLAY_NAME],
        )
    else:
        last_pid = last_known_state.get('pid')
        add(
            'process',
            'hades2.diagnostics.check.process',
            False,
            'hades2.diagnostics.detail.unavailableLastPid' if last_pid else 'hades2.diagnostics.detail.unavailable',
            name_arguments=[DISPLAY_NAME],
            detail_arguments=[last_pid] if last_pid else None,
        )
    add(
        'luaConnection',
        'hades2.diagnostics.check.luaConnection',
        bool(state.get('connected')),
        state.get('status', 'unknown') if runtime_observation_available else 'hades2.diagnostics.detail.unavailable',
    )
    diag = state.get('runtimeDiagnostics', {}) if isinstance(state.get('runtimeDiagnostics'), dict) else {}
    revision = diag.get('revision')
    add(
        'luaRevision',
        'hades2.diagnostics.check.luaRevision',
        revision is not None,
        revision if revision is not None else 'hades2.diagnostics.detail.disconnected',
    )
    add(
        'currentScene',
        'hades2.diagnostics.check.currentScene',
        state.get('scene') in ('run', 'crossroads'),
        state.get('scene', 'unknown'),
    )
    hero_id = diag.get('heroObjectId')
    add(
        'heroObjectId',
        'hades2.diagnostics.check.heroObjectId',
        hero_id is not None,
        hero_id if hero_id is not None else 'hades2.diagnostics.detail.notAvailable',
    )
    run_count = state.get('runCount')
    add(
        'runCount',
        'hades2.diagnostics.check.runCount',
        run_count is not None,
        run_count if run_count is not None else 'hades2.diagnostics.detail.notAvailable',
    )

    fs = state.get('featureSupport', {}) if isinstance(state.get('featureSupport'), dict) else {}
    # schema.TOGGLES owns Hades durable toggle identity. gameSpeed is the one
    # explicit Core-owned capability projected into the same runtime-support
    # report, so it is appended here rather than copied into another Hades list.
    diagnostic_features = list(schema.TOGGLES)
    for key in ('damageMultiplier', 'gameSpeed'):
        if key not in diagnostic_features:
            diagnostic_features.append(key)
    for key in diagnostic_features:
        supported = fs.get(key) is True
        add(
            f'featureSupport.{key}',
            'hades2.diagnostics.check.featureSupport',
            supported,
            'hades2.diagnostics.detail.supported' if supported else 'hades2.diagnostics.detail.unsupported',
            name_arguments=[_feature_label_key(key)],
        )
    ss = state.get('statSupport', {}) if isinstance(state.get('statSupport'), dict) else {}
    for key in (k for k in STAT_RULES if k != 'grasp'):
        supported = ss.get(key) is True
        add(
            f'statSupport.{key}',
            'hades2.diagnostics.check.statSupport',
            supported,
            'hades2.diagnostics.detail.supported' if supported else 'hades2.diagnostics.detail.unsupported',
            name_arguments=[_STAT_LABEL_KEYS.get(key, key)],
        )
    cast = diag.get('castRuntime', {}) if isinstance(diag.get('castRuntime'), dict) else {}
    add(
        'castRuntime',
        'hades2.diagnostics.check.castRuntime',
        bool(fs.get('instantCastCooldown')),
        json.dumps(cast, ensure_ascii=False, default=str),
    )
    hexdiag = diag.get('hexRuntime', {}) if isinstance(diag.get('hexRuntime'), dict) else {}
    add(
        'hexRuntime',
        'hades2.diagnostics.check.hexRuntime',
        bool(fs.get('hexAlwaysReady')),
        json.dumps(hexdiag, ensure_ascii=False, default=str),
    )
    return {
        'checks': checks,
        'passed': sum(1 for item in checks if item['ok']),
        'total': len(checks),
        'state': dict(state),
        'profiles': adapter.list_profiles(),
        'protocolVersion': HOST_PROTOCOL_VERSION,
        'moduleProtocolVersion': adapter.module_protocol_version,
        'backendVersion': APP_BACKEND_VERSION,
    }
