"""Hades I basket conflicts include the opposite side of a parent entry."""
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))
sys.path.insert(0, str(ROOT / 'tests/fixtures'))

from hades_save import Entries, build_save, environment, root_state
from games.hades.save_document import HadesSaveDocument
from games.hades.save_workspace import HadesSaveWorkspace, physical
from games.hades import save_values as values


def stage(workspace, path, operation, value=None):
    identifier = values.identifier(path, workspace.baseline_generation) if isinstance(path, tuple) else path
    return workspace.stage(identifier, operation, value, baseline_generation=workspace.baseline_generation)


def rejects_overlap(workspace, action):
    before = workspace.review()
    try:
        action()
    except ValueError as error:
        assert 'overlap' in str(error)
    else:
        raise AssertionError('An ancestor key and its value descendant entered the same basket')
    assert workspace.review() == before


with tempfile.TemporaryDirectory(prefix='mgt-hades-editor-conflicts-') as temporary:
    saves, service = environment(Path(temporary))
    source = {'rootId': 'main', 'relativePath': 'Profile1.sav'}
    target = {'rootId': 'main', 'relativePath': 'Profile2.sav'}
    original_source = (saves / 'Profile1.sav').read_bytes()
    original_target = (saves / 'Profile2.sav').read_bytes()

    for operation, replacement in (('unset', None), ('set', values.typed('RenamedOwner'))):
        for parent_first in (False, True):
            workspace = HadesSaveWorkspace.open(service, source=source, target=target)
            parent = physical(workspace.document, ('GameState', 'UnknownFutureField'))
            key = parent[:-1] + (parent[-1] - 1,)
            child = physical(workspace.document, ('GameState', 'UnknownFutureField', 'Marker'))
            parent_edit = lambda: stage(workspace, key, operation, replacement)
            child_edit = lambda: stage(workspace, child, 'set', values.typed('retained-child-edit'))
            first, second = (parent_edit, child_edit) if parent_first else (child_edit, parent_edit)
            first()
            rejects_overlap(workspace, second)
            assert workspace.review()['count'] == 1

    for owner in (('GameState',), ('GameState', 'Resources')):
        for parent_first in (False, True):
            workspace = HadesSaveWorkspace.open(service, source=source, target=target)
            parent = physical(workspace.document, owner)
            key = parent[:-1] + (parent[-1] - 1,)
            parent_edit = lambda: stage(workspace, key, 'unset')
            resource_edit = lambda: stage(workspace, 'resource:MetaPoints', 'set', values.typed(20))
            first, second = (parent_edit, resource_edit) if parent_first else (resource_edit, parent_edit)
            first()
            rejects_overlap(workspace, second)
            assert workspace.review()['count'] == 1

    assert (saves / 'Profile1.sav').read_bytes() == original_source
    assert (saves / 'Profile2.sav').read_bytes() == original_target

    # Neither edit replaces the containing entry: table-key and table-value
    # descendants retain independent physical ownership.
    native = root_state()
    native['GameState']['UnknownFutureField'] = Entries([
        (Entries([('KeyLeaf', 1)]), Entries([('ValueLeaf', 2)])),
        ('Sibling', 3),
    ])
    (saves / 'Profile1.sav').write_bytes(build_save(state=native))
    workspace = HadesSaveWorkspace.open(service, source=source, target=target)
    parent = physical(workspace.document, ('GameState', 'UnknownFutureField'))
    stage(workspace, parent + (0, 1), 'set', values.typed(11))
    stage(workspace, parent + (1, 1), 'set', values.typed(22))
    stage(workspace, parent + (3,), 'set', values.typed(33))
    assert workspace.review()['count'] == 3
    receipt = workspace.apply(baseline_generation=workspace.baseline_generation)
    assert receipt['applied'] and receipt['verified']
    installed = HadesSaveDocument.load(saves / 'Profile2.sav').lua_state['GameState']['UnknownFutureField']
    key, value = installed.entries()[0]
    assert key['KeyLeaf'] == 11 and value['ValueLeaf'] == 22 and installed['Sibling'] == 33

print('hades_save_editor_parent_key_conflicts_and_independent_descendants_ok')
