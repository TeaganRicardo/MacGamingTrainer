"""Offline workloads verify phase joins, counts and finite native inventories."""
import os
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'Tools'), str(ROOT / 'Backend'), str(ROOT / 'tests')]
from hades2_profile_workloads import profile_end_to_end, profile_save_queries, profile_time_warp, read_records
from profile_hades2_operations import profile_resident, summarize

# This fixture is also the worker used by the Swift Host workload below. Its
# successful-result protocol must remain covered on machines without swiftc.
# Cross the real backend/router/resident/client/worker/Lua owners repeatedly so
# a missing ACK method cannot turn the first accepted result into terminal loss.
with tempfile.TemporaryDirectory(prefix='mgt-profile-backend-protocol-') as temporary:
    folder = Path(temporary)
    events = folder / 'events.log'
    requests = [
        {'id': 'cold', 'command': 'status', 'params': {}},
        {'id': 'edit', 'command': 'set_resource', 'params': {'resource': 'MetaCurrency', 'amount': 123}},
        {'id': 'spawn', 'command': 'spawn_reward', 'params': {'reward': 'MetaCurrencyDrop'}},
        {'id': 'warm', 'command': 'status', 'params': {}},
    ]
    run = subprocess.run(
        [sys.executable, str(ROOT / 'Tools/fixtures/hades2_profile_backend.py')],
        input=''.join(json.dumps(request) + '\n' for request in requests),
        env=dict(os.environ, MGT_PROFILE_OPERATIONS='1', MGT_PROFILE_TEMP=str(folder),
                 MGT_PROFILE_EVENTS=str(events), MGT_PROFILE_SOURCE_ROOT=str(ROOT),
                 MGT_PROFILE_TRAITS='8', MGT_PROFILE_CATALOG='16', MGT_PROFILE_RESOURCES='8'),
        capture_output=True, text=True, timeout=30, check=True,
    )
    replies = [json.loads(line) for line in run.stdout.splitlines()]
    assert [reply['id'] for reply in replies] == [request['id'] for request in requests]
    failures = [(reply['id'], reply.get('error')) for reply in replies if not reply['ok']]
    assert not failures, failures[0]
    observed = {}
    for reply in replies:
        observed.update(reply['result'])
        assert observed['connected'] and observed['status'] != 'restart_required'
        if reply['id'] == 'edit':
            assert next(row for row in observed['resources'] if row['id'] == 'MetaCurrency')['count'] == 123
        if reply['id'] == 'spawn':
            assert observed['applied'] and observed['lastAction']['outcome'] == 'completed'
    assert next(row for row in observed['resources'] if row['id'] == 'MetaCurrency')['count'] == 123
    records = read_records(events.read_text())
    for request in requests:
        rows = [row for row in records if row['request_id'] == request['id']]
        rpc = [row['method'] for row in rows if row['phase'] == 'sidecar.rpc']
        assert rpc == ['transport.execute', 'transport.acknowledge_result'], (request['id'], rpc)
        # The cold bootstrap replaces the instrumented resident. Each later
        # operation enters it once; ACK must not dispatch another Lua command.
        if request['id'] != 'cold':
            assert sum(row['phase'] == 'resident.materialize_dispatch' for row in rows) == 1, rows

resident = profile_resident(2, 8, 16, 8)
assert resident['fixture']['mounted_traits'] == 8 and resident['fixture']['catalog_traits'] == 16
assert resident['fixture']['resources'] == 8 and resident['fixture']['stats']
assert resident['fixture']['native_upgrade_queries_per_status'] == 1
assert {'frame_with_desired', 'frame_without_desired', 'status_json', 'status_dispatch'} <= resident['metrics'].keys()
scenarios = {row['scenario']: row for row in resident['maintenance']}
assert scenarios.keys() == {'features', 'locks', 'missing_hero', 'owner_transition'}
for name, row in scenarios.items():
    assert row['frames'] == (2 if name == 'owner_transition' else 200)
    assert row['phases']['synchronize']['calls'] == row['frames']
    assert row['phases']['reconcileDesired']['calls'] == row['frames']
    assert row['phases']['enforceLocks']['calls'] == row['frames']
assert scenarios['locks']['native_calls']['UpdateHealthUI'] > 0
assert scenarios['missing_hero']['native_calls'].get('UpdateHealthUI', 0) == 0
query = profile_save_queries(2, 50, summarize)
assert {'cold_index', 'source_refresh', 'warm_query', 'warm_query_after_refresh', 'warm_query_empty',
        'warm_query_filtered', 'warm_query_text_en', 'warm_query_text_zh'} == query['metrics'].keys()
assert query['fixture']['history_scenes'] == 250 and query['fixture']['known_scene_records'] == 275
assert all(value['count'] == 2 for value in query['metrics'].values())
warp = profile_time_warp(2, summarize)
assert {'never_enabled', 'active_2x', 'enabled_then_reset_1x'} == warp['metrics'].keys()
assert all(value['count'] == 2 for value in warp['metrics'].values())
if shutil.which('swiftc'):
    end = profile_end_to_end(2, 8, 16, 8, summarize)
    assert end['observed']
    assert end['sidecar_calls']['transport.execute'] > 0 and all(value > 0 for value in end['bytes'].values())
    assert end['sidecar_calls']['transport.acknowledge_result'] == end['sidecar_calls']['transport.execute']
    assert {'host.admission', 'host.request_queue', 'host.payload_decode', 'host.payload_apply',
        'backend.routing', 'backend.reply_serialize', 'backend.reply_ready',
        'sidecar.dispatch', 'sidecar.reply_serialize_write', 'resident.materialize_dispatch',
        'resident.json_serialize', 'resident.json_decode', 'resident.localization'} <= end['phases'].keys()
    for rows in end['requests'].values():
        if any(row.get('path') == 'warm_status' for row in rows):
            calls = [row for row in rows if row['phase'] == 'sidecar.rpc']
            assert any(row['method'] == 'transport.execute' for row in calls)
            assert all(row.get('response_kind', 'full') == 'full' for row in rows)
    assert 'cold_catalog' in end['paths'] and 'active_status' in end['paths']
print('hades2_profile_workloads_ok')
