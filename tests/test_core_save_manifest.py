from pathlib import Path
import json
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))

from core.module_manifest import GameModuleManifest, ManifestError


def base_manifest():
    return {
        'id': 'example',
        'displayName': 'Example Game',
        'protocolVersion': 1,
        'backend': {'adapter': 'games.example.adapter:ExampleAdapter'},
        'targetApplication': {
            'processName': 'Example Game',
            'bundleIdentifier': 'com.example.game',
        },
        'saveManagement': {
            'roots': [
                {
                    'id': 'main',
                    'path': '~/Library/Application Support/Example Game',
                    'include': ['Profile*.sav', 'activeProfile', 'saveinfo'],
                }
            ],
            'provider': None,
            'hotBackup': True,
            'restorePolicy': 'hotPreferred',
            'stagedRestore': True,
        },
    }


def load(data):
    with tempfile.TemporaryDirectory(prefix='mgt-save-manifest-') as tmp:
        path = Path(tmp) / 'module.json'
        path.write_text(json.dumps(data), encoding='utf-8')
        return GameModuleManifest.load(path)


def rejected(data):
    try:
        load(data)
    except ManifestError:
        return
    raise AssertionError('unsafe save-management declaration was accepted')


manifest = load(base_manifest())
assert manifest.save_management.hot_backup is True
assert manifest.save_management.restore_policy == 'hotPreferred'
assert manifest.save_management.staged_restore is True
assert len(manifest.save_management.roots) == 1
root = manifest.save_management.roots[0]
assert root.id == 'main'
assert root.path == '~/Library/Application Support/Example Game'
assert root.include == ('Profile*.sav', 'activeProfile', 'saveinfo')

public = manifest.public_metadata()['saveManagement']
assert public == {
    'supported': True,
    'hotBackup': True,
    'restorePolicy': 'hotPreferred',
    'stagedRestore': True,
}
assert 'roots' not in public and 'provider' not in public
assert 'Example Game' not in repr(public)

without_save = base_manifest()
del without_save['saveManagement']
assert load(without_save).save_management is None
assert 'saveManagement' not in load(without_save).public_metadata()

bad = base_manifest(); bad['saveManagement']['roots'][0]['id'] = 'Bad-ID'; rejected(bad)
bad = base_manifest(); bad['saveManagement']['roots'].append(dict(bad['saveManagement']['roots'][0])); rejected(bad)
bad = base_manifest(); bad['saveManagement']['roots'][0]['include'] = []; rejected(bad)
bad = base_manifest(); bad['saveManagement']['roots'][0]['include'] = ['../Profile1.sav']; rejected(bad)
bad = base_manifest(); bad['saveManagement']['roots'][0]['include'] = ['/tmp/Profile1.sav']; rejected(bad)
bad = base_manifest(); bad['saveManagement']['provider'] = 'other.pkg:Provider'; rejected(bad)
bad = base_manifest(); bad['saveManagement']['hotBackup'] = 1; rejected(bad)
bad = base_manifest(); bad['saveManagement']['stagedRestore'] = 'yes'; rejected(bad)
bad = base_manifest(); bad['saveManagement']['restorePolicy'] = 'alwaysHot'; rejected(bad)

provider = base_manifest()
provider['saveManagement']['provider'] = 'games.example.save_provider:ExampleProvider'
assert load(provider).save_management.provider == 'games.example.save_provider:ExampleProvider'

print('core_save_manifest_ok')
