"""A read-only report of observed Hades state and its bundled contract."""
from datetime import datetime, timezone
import json
import platform
import sys

from core.protocol import HOST_PROTOCOL_VERSION


def build_diagnostics(adapter, state):
    manifest = json.loads((adapter.context.module_dir / 'module.json').read_text(encoding='utf-8'))
    checks = [
        {'name': 'hades.diagnostics.backend', 'ok': True,
         'detail': f'{sys.version.split()[0]} · {platform.platform()}'},
        {'name': 'hades.diagnostics.protocol', 'ok': True,
         'detail': f'Host {HOST_PROTOCOL_VERSION} · Hades {adapter.module_protocol_version}'},
        {'name': 'hades.diagnostics.connection', 'ok': state['connected'],
         'detail': str(state.get('pid') or '')},
        {'name': 'hades.diagnostics.hero', 'ok': bool(state.get('heroReady')),
         'detail': str((state.get('target') or {}).get('heroId', ''))},
        {'name': 'hades.diagnostics.speed',
         'ok': adapter._game_speed_actual is not None and adapter._game_speed_error is None,
         'detail': json.dumps(adapter._game_speed_projection(), ensure_ascii=False)},
    ]
    return {'generatedAt': datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'gameID': 'hades', 'supportedBuild': manifest['supportedBuild'],
            'checks': checks, 'state': state, 'desired': adapter.preferences.load()}
