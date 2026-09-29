import json
import plistlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def fixture(root):
    for directory in ('Backend', 'Tools', 'Sources', 'Resources', 'docs/reference/hades2'):
        shutil.copytree(ROOT / directory, root / directory,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    for name in ('Info.plist', 'ACTIVE_GAME_ID'):
        shutil.copy2(ROOT / name, root / name)


def run(root, tool, *args):
    return subprocess.run([sys.executable, str(root / 'Tools' / tool), *map(str, args)],
                          cwd=root, text=True, capture_output=True)


class AppIdentityContract(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='mgt-app-identity-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        fixture(self.root)

    def test_root_identity_reintroduction_is_rejected(self):
        plist = self.root / 'Info.plist'
        data = plistlib.loads(plist.read_bytes())
        data['CFBundleDisplayName'] = 'Wrong Root Name'
        data['CFBundleName'] = 'Wrong Root Name'
        data['CFBundleIdentifier'] = 'com.example.wrong'
        plist.write_bytes(plistlib.dumps(data))
        result = run(self.root, 'validate_game_module.py', 'hades2')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Info.plist', result.stderr)
        self.assertIn('CFBundleDisplayName', result.stderr)

    def test_duplicate_output_identity_is_rejected(self):
        fixture_root = self.root / 'ContractFixtures/reference_module'
        shutil.copytree(ROOT / 'ContractFixtures/reference_module/backend',
                        self.root / 'Backend/games/reference_fixture')
        shutil.copytree(ROOT / 'ContractFixtures/reference_module/frontend',
                        self.root / 'Sources/ReferenceFixture')
        path = self.root / 'Backend/games/reference_fixture/module.json'
        manifest = json.loads(path.read_text())
        for duplicate in ('Mac Gaming Trainer', 'mac gaming trainer'):
            with self.subTest(duplicate=duplicate):
                manifest['app']['displayName'] = duplicate
                path.write_text(json.dumps(manifest))
                result = run(self.root, 'validate_game_module.py', 'reference_fixture')
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('displayName', result.stderr)
                self.assertIn('hades2', result.stderr)

    def test_duplicate_bundle_identifier_is_rejected(self):
        shutil.copytree(ROOT / 'ContractFixtures/reference_module/backend',
                        self.root / 'Backend/games/reference_fixture')
        shutil.copytree(ROOT / 'ContractFixtures/reference_module/frontend',
                        self.root / 'Sources/ReferenceFixture')
        path = self.root / 'Backend/games/reference_fixture/module.json'
        manifest = json.loads(path.read_text())
        manifest['app']['bundleIdentifier'] = 'COM.GAO.MACGAMINGTRAINER'
        path.write_text(json.dumps(manifest))
        result = run(self.root, 'validate_game_module.py', 'reference_fixture')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('bundleIdentifier', result.stderr)
        self.assertIn('hades2', result.stderr)

    def test_packaged_executable_is_verified_against_root_owner(self):
        manifest = json.loads((self.root / 'Backend/games/hades2/module.json').read_text())
        app = self.root / 'dist' / (manifest['app']['displayName'] + '.app')
        contents = app / 'Contents'
        resources = contents / 'Resources'
        game = resources / 'Backend/games/hades2'
        game.mkdir(parents=True)
        (resources / 'ACTIVE_GAME_ID').write_text('hades2\n')
        (game / 'module.json').write_text(json.dumps(manifest))
        info = plistlib.loads((self.root / 'Info.plist').read_bytes())
        info['CFBundleIdentifier'] = manifest['app']['bundleIdentifier']
        info['CFBundleName'] = manifest['app']['displayName']
        info['CFBundleDisplayName'] = manifest['app']['displayName']
        (contents / 'Info.plist').write_bytes(plistlib.dumps(info))
        result = run(self.root, 'verify_module_build.py', 'hades2', '--dist-dir', self.root / 'dist')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('executable', result.stderr.lower())


if __name__ == '__main__':
    unittest.main()
