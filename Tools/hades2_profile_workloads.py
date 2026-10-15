"""Bounded offline workloads and evidence assembly for #465 (no real game/save)."""
from __future__ import annotations
import collections
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def phase_summary(records, summarize):
    phases = collections.defaultdict(list)
    calls, byte_counts = collections.Counter(), collections.Counter()
    for record in records:
        if not record.get('phase') or not isinstance(record.get('seconds'), (int, float)):
            raise ValueError('invalid phase record')
        phases[record['phase']].append(record['seconds'])
        if record['phase'] == 'sidecar.rpc':
            calls[record['method']] += 1
            byte_counts['sidecar_request'] += record['request_bytes']
            byte_counts['sidecar_reply'] += record['reply_bytes']
        if record['phase'] in ('backend.stdout_serialize', 'backend.reply_ready'):
            byte_counts['backend_reply'] += record['reply_bytes']
    return {'phases': {key: summarize(value) for key, value in phases.items()},
            'sidecar_calls': dict(calls), 'bytes': dict(byte_counts)}


def read_records(raw):
    records = []
    for line in raw.splitlines():
        if 'OperationProfile ' in line:
            records.append(json.loads(line.split('OperationProfile ', 1)[1]))
    return records


def profile_end_to_end(samples, traits, catalog_traits, resources, summarize, source=ROOT, probes=True):
    compiler = shutil.which('swiftc')
    if compiler is None:
        return {'observed': False, 'reason': 'swiftc unavailable; Host admission/decode/apply unobserved'}
    with tempfile.TemporaryDirectory(prefix='mgt-profile-e2e-') as temporary:
        folder = Path(temporary)
        main = folder / 'main.swift'
        main.write_bytes((ROOT / 'Tools/fixtures/hades2_profile_host.swift').read_bytes())
        binary = folder / 'host'
        subprocess.run([compiler, '-O', *(str(source / ('Sources/Core/Runtime/' + name + '.swift'))
            for name in ('BackendProcess', 'BackendClient', 'TrainerBackendSession')),
            str(main), '-o', str(binary)], check=True, capture_output=True, text=True, timeout=60)
        events = folder / 'events.log'
        environment = dict(os.environ, MGT_PROFILE_OPERATIONS='1' if probes else '0', MGT_PROFILE_TEMP=str(folder),
                           MGT_PROFILE_EVENTS=str(events), MGT_PROFILE_SOURCE_ROOT=str(source),
                           MGT_PROFILE_TRAITS=str(traits), MGT_PROFILE_CATALOG=str(catalog_traits),
                           MGT_PROFILE_RESOURCES=str(resources))
        module = json.loads((source / 'Backend/games/hades2/module.json').read_text())
        run = subprocess.run([str(binary), str(ROOT / 'Tools/fixtures/hades2_profile_backend.py'),
                              sys.executable, str(samples), str(module['protocolVersion'])],
                             env=environment, check=False, capture_output=True, text=True, timeout=120)
        if run.returncode:
            raise RuntimeError('offline Host failed: ' + run.stdout[-3000:] + run.stderr[-3000:] + events.read_text()[-4000:])
        records = read_records(run.stdout) + read_records(events.read_text())
    # A pre-probe worker knows its RPC id, while the enclosing backend request
    # records that id at the outgoing seam. Join without any state bodies.
    joins = {row['rpc_id']: (row['request_id'], row['command'])
             for row in records if row['phase'] == 'sidecar.identity'}
    for row in records:
        identity = row['request_id']
        if identity.startswith('rpc-') and identity[4:] in joins:
            row['request_id'], row['command'] = joins[identity[4:]]
    groups = collections.defaultdict(list)
    for row in records:
        groups[row['request_id']].append(row)
    workload_by_id = {row['request_id']: row.get('workload') for row in records
                      if row['phase'] == 'harness.host_round_trip'}
    cold_id = next(key for key, value in workload_by_id.items() if value == 'sample-1')
    paths = {'cold': phase_summary(groups[cold_id], summarize),
             'warm': phase_summary([row for row in records if row['request_id'] in workload_by_id
                                    and row['request_id'] != cold_id], summarize)}
    for path in ('cold_catalog', 'warm_status', 'resource_edit', 'active_status', 'queued_status'):
        identities = {row['request_id'] for row in records if row.get('path') == path}
        paths[path] = phase_summary([row for row in records if row['request_id'] in identities], summarize)
    return {'observed': True, 'probes_enabled': probes, 'workload': 'production Host/Core/Hades adapter/session/RPC/Lua; synthetic natives; temp stores',
            'fixture': {'mounted_traits': traits, 'catalog_traits': catalog_traits, 'resources': resources},
            'payload_application': 'real TrainerBackendSession callback into an opaque dictionary fixture',
            'clock': 'local monotonic wall time except resident os.clock CPU; nested intervals overlap',
            'paths': paths, **phase_summary(records, summarize), 'requests': dict(groups),
            'unobserved': ['real debugger/engine boundary (separate helper probe)', 'SwiftUI rendering/main-game FPS',
                          'resident native callbacks/presentation/yield time']}


def profile_save_queries(samples, scenes, summarize):
    # Temporary sources exercise the current public read-only owner. Neither
    # workspace entry nor backup/write-target semantics are overridden.
    from games.hades2 import save_investigation as investigation
    from games.hades2.save_document import LuaTable
    timings = collections.defaultdict(list)
    with tempfile.TemporaryDirectory(prefix='mgt-profile-save-query-') as temporary:
        root = Path(temporary)
        scripts = root / 'sources/Scripts'; scripts.mkdir(parents=True)
        story = scripts / 'StoryResetData.lua'
        story.write_text('StoryResetData = { TextLines = {} }\n')
        expected = hashlib.sha256(story.read_bytes()).hexdigest()
        script = scripts / 'NPCData_Nemesis.lua'
        script.write_text('UnitSetData = {\n' + '\n'.join(
            '  NemesisAboutChronos%05d = { { Cue = "/VO/Nemesis_%05d", Text = "Chronos fixture %d" } },' % (i, i, i)
            for i in range(scenes)) + '\n}\n')
        for language in ('en', 'zh-CN'):
            text = root / ('sources/Text/' + language); text.mkdir(parents=True)
            (text / 'NPCData.sjson').write_text('{ Texts = [\n' + '\n'.join(
                '{ Id = %s DisplayName = %s Event = %s }' % (json.dumps('Nemesis_%05d' % i),
                    json.dumps(('Chronos English profile ' if language == 'en' else '克罗诺斯 样本 ') + str(i), ensure_ascii=False),
                    json.dumps('NemesisAboutChronos%05d' % i))
                for i in range(scenes)) + '\n] }\n')
        def table(entries):
            return LuaTable(0, len(entries), entries)
        history_count = scenes * 5
        records = [('NemesisAboutChronos%05d' % i, True) for i in range(scenes // 2)]
        records += [('HistoryDialogue%05d' % i, True) for i in range(history_count)]
        state = table([('GameState', table([('TextLinesRecord', table(records)),
            ('RunHistory', LuaTable(history_count, 0, [(i + 1, table([('RunIndex', i)])) for i in range(history_count)]))]))])
        queries = {
            'warm_query': ('Chronos', 'zh-CN', 'all', scenes),
            'warm_query_empty': ('', 'zh-CN', 'all', len(records)),
            'warm_query_filtered': ('Chronos', 'zh-CN', 'recorded', scenes // 2),
            'warm_query_text_en': ('English profile', 'en', 'all', scenes),
            'warm_query_text_zh': ('克罗诺斯 样本', 'zh-CN', 'all', scenes),
        }
        def query(owner, definition=queries['warm_query']):
            search, language, state_filter, expected = definition
            result = owner.query(state, search=search, offset=0, limit=50, language=language,
                                 permissions={}, state_filter=state_filter)
            assert result['total'] >= expected and len(result['items']) == min(50, result['total'])
            return result
        for index in range(samples):
            # Every distinct source has the same scale and a new identity. The
            # public constructor therefore performs cold parse/index work.
            with script.open('a') as stream: stream.write('-- cold fixture %d\n' % index)
            started = time.perf_counter()
            owner = investigation.NativeDialogueInvestigation(root, expected_hash=expected)
            timings['cold_index'].append(time.perf_counter() - started)
            for name, definition in queries.items():
                started = time.perf_counter(); query(owner, definition)
                timings[name].append(time.perf_counter() - started)
            with script.open('a') as stream: stream.write('-- refresh fixture %d\n' % index)
            started = time.perf_counter(); owner._refresh()
            timings['source_refresh'].append(time.perf_counter() - started)
            started = time.perf_counter(); query(owner)
            timings['warm_query_after_refresh'].append(time.perf_counter() - started)
    return {'workload': 'public NativeDialogueInvestigation with temporary bilingual scripts and static LuaTable',
            'fixture': {'scenes': scenes, 'recorded_scenes': scenes // 2, 'history_scenes': history_count,
                        'known_scene_records': len(records), 'queries': {key: list(value[:3]) for key, value in queries.items()}, 'page_size': 50},
            'clock': 'perf_counter wall time; warm query includes owning public freshness check',
            'metrics': {name: summarize(values) for name, values in timings.items()}}


def profile_time_warp(samples, summarize, source=ROOT):
    with tempfile.TemporaryDirectory(prefix='mgt-profile-clock-') as temporary:
        folder = Path(temporary)
        # Reuse the existing portable native harness's type/OS stubs without
        # importing its top-level test execution.
        import ast
        tree = ast.parse((ROOT / 'tests/test_process_time_warp_install_contract.py').read_text())
        stub_node = next(node for node in tree.body if isinstance(node, ast.Assign)
                         and any(isinstance(target, ast.Name) and target.id == 'stubs' for target in node.targets))
        stubs = ast.literal_eval(stub_node.value)
        for relative, content in stubs.items():
            path = folder / relative; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(content)
        binary = folder / 'clock'
        native = source / 'Native/ProcessTimeWarp'
        subprocess.run(['cc', '-O2', '-std=c11', '-D_DEFAULT_SOURCE', '-I', str(folder),
                        '-I', str(native), '-I', str(native / 'vendor/fishhook'),
                        str(ROOT / 'Tools/fixtures/hades2_time_warp_profile.c'), '-lm', '-o', str(binary)],
                       check=True, capture_output=True, text=True, timeout=30)
        run = subprocess.run([str(binary), str(samples)], check=True, capture_output=True, text=True, timeout=30)
    metrics = collections.defaultdict(list)
    for line in run.stdout.splitlines():
        name, seconds = line.split('\t'); metrics[name].append(float(seconds))
    return {'workload': 'production native warped clock functions with explicit dyld/time stubs; 100000 calls per sample',
            'clock': 'process CPU seconds per call; volatile synthetic clock source',
            'unobserved': ['actual engine import call frequency', 'real dyld/fishhook binding', 'contention/game FPS'],
            'metrics': {name: summarize(values) for name, values in metrics.items()}}
