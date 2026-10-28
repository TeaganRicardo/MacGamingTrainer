"""Captured controls cannot cross a verified Hades document baseline."""
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))
sys.path.insert(0, str(ROOT / 'tests/fixtures'))

from hades_save import build_save, environment, root_state
from games.hades.save_document import HadesSaveDocument
from games.hades.save_workspace import HadesSaveWorkspace, physical
from games.hades import save_values as values


def rejects(action):
    try: action()
    except ValueError: return
    raise AssertionError('A stale control crossed its captured document baseline')


def entry(workspace, keys):
    return values.identifier(physical(workspace.document, keys), workspace.baseline_generation)


with tempfile.TemporaryDirectory(prefix='mgt-hades-editor-authority-') as temporary:
    saves, service = environment(Path(temporary))
    native = root_state()
    native['GameState']['UnknownFutureField'] = {'A': 1, 'B': 2, 'C': 3}
    (saves / 'Profile1.sav').write_bytes(build_save(state=native))
    source = {'rootId': 'main', 'relativePath': 'Profile1.sav'}
    target = {'rootId': 'main', 'relativePath': 'Profile2.sav'}
    workspace = HadesSaveWorkspace.open(service, source=source, target=target)
    independent = HadesSaveWorkspace.open(service, source=source, target=target)
    original_source_hash = workspace.session.source_sha256
    old_generation = workspace.baseline_generation
    old_parent = entry(workspace, ('GameState', 'UnknownFutureField'))
    old_a = entry(workspace, ('GameState', 'UnknownFutureField', 'A'))
    old_b = entry(workspace, ('GameState', 'UnknownFutureField', 'B'))
    old_b_row = workspace.detail(old_b)['row']
    assert old_b_row['baselineGeneration'] == old_generation
    workspace.stage(old_a, 'unset', baseline_generation=old_generation)
    receipt = workspace.apply(baseline_generation=old_generation)
    new_generation = receipt['baselineGeneration']
    assert new_generation != old_generation and new_generation == workspace.summary()['baselineGeneration']
    assert workspace.query(domain='advanced')['baselineGeneration'] == new_generation
    assert workspace.review()['baselineGeneration'] == new_generation
    assert workspace.session.source_sha256 == original_source_hash
    installed = HadesSaveDocument.load(saves / 'Profile2.sav').lua_state['GameState']['UnknownFutureField']
    assert installed.entries() == (('B', 2), ('C', 3))

    # This is the queue order of the escaped UI bug: Apply removes A, then an
    # already rendered B control arrives with B's old occurrence index.
    rejects(lambda: workspace.stage(old_b_row['id'], 'set', values.typed(99),
                                    baseline_generation=old_b_row['baselineGeneration']))
    assert workspace.review()['count'] == 0
    rejects(lambda: workspace.stage(old_b, 'set', values.typed(99), baseline_generation=new_generation))
    rejects(lambda: workspace.detail(old_b))
    rejects(lambda: workspace.query(domain='advanced', parentId=old_parent))
    rejects(lambda: workspace.stage('resource:MetaPoints', 'set', values.typed(99), baseline_generation=old_generation))
    rejects(lambda: workspace.set_target(source, baseline_generation=old_generation))
    rejects(lambda: workspace.cancel(baseline_generation=old_generation))
    rejects(lambda: workspace.unstage(old_b, baseline_generation=old_generation))
    rejects(lambda: workspace.apply(baseline_generation=old_generation))
    rejects(lambda: workspace.stage('resource:MetaPoints', 'set', values.typed(99), baseline_generation=None))
    assert workspace.session.target == target

    # A replacement can reorder every child without closing the workspace.
    fresh_b = entry(workspace, ('GameState', 'UnknownFutureField', 'B'))
    replacement = {'luaType': 'table', 'arraySize': 0, 'hashSize': 1, 'entries': [
        {'key': values.typed('Replacement'), 'value': values.typed(17)}]}
    workspace.stage(entry(workspace, ('GameState', 'UnknownFutureField')), 'set', replacement,
                    baseline_generation=new_generation)
    second = workspace.apply(baseline_generation=new_generation)
    assert second['baselineGeneration'] not in (old_generation, new_generation)
    rejects(lambda: workspace.stage(fresh_b, 'set', values.typed(77), baseline_generation=new_generation))
    assert workspace.review()['count'] == 0
    installed = HadesSaveDocument.load(saves / 'Profile2.sav').lua_state['GameState']['UnknownFutureField']
    assert installed.entries() == (('Replacement', 17),)
    assert workspace.session.source_sha256 == original_source_hash

    # A different editor has a distinct baseline even over identical bytes.
    assert independent.baseline_generation not in (old_generation, new_generation, second['baselineGeneration'])
    rejects(lambda: independent.stage(old_b, 'set', values.typed(66), baseline_generation=old_generation))
    rejects(lambda: independent.stage(old_b, 'set', values.typed(66), baseline_generation=independent.baseline_generation))
    assert independent.review()['count'] == 0
    independent.stage(entry(independent, ('GameState', 'UnknownFutureField', 'B')), 'set', values.typed(22),
                      baseline_generation=independent.baseline_generation)
    assert independent.review()['count'] == 1 and workspace.review()['count'] == 0

print('hades_save_editor_baseline_authority_and_stale_control_non_redirect_ok')
