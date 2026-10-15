"""Offline workloads verify phase joins, counts and finite native inventories."""
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'Tools'), str(ROOT / 'Backend'), str(ROOT / 'tests')]
from hades2_profile_workloads import profile_end_to_end, profile_save_queries, profile_time_warp
from profile_hades2_operations import profile_resident, summarize

resident = profile_resident(2, 8, 16, 8)
assert resident['fixture']['mounted_traits'] == 8 and resident['fixture']['catalog_traits'] == 16
assert resident['fixture']['resources'] == 8 and resident['fixture']['stats']
assert resident['fixture']['native_upgrade_queries_per_status'] == 1
assert {'frame_with_desired', 'frame_without_desired', 'status_json', 'status_dispatch'} <= resident['metrics'].keys()
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
