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
    for directory in ('Backend', 'Tools', 'Sources', 'Resources',
                      'docs/reference/hades', 'docs/reference/hades2'):
        shutil.copytree(ROOT / directory, root / directory,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    for name in ('Info.plist', 'app.json'):
        shutil.copy2(ROOT / name, root / name)


def run(root, tool, *args):
    return subprocess.run([sys.executable, str(root / 'Tools' / tool), *map(str, args)],
                          cwd=root, text=True, capture_output=True)


def resolved_app(root, selection):
    if selection == 'all':
        result = run(root, 'product_support.py', 'all')
    else:
        result = run(root, 'validate_game_module.py', selection, '--json')
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return json.loads(result.stdout)['app']


class AppIdentityContract(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='mgt-app-identity-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        fixture(self.root)

    def add_reference_module(self):
        shutil.copytree(ROOT / 'ContractFixtures/reference_module/backend',
                        self.root / 'Backend/games/reference_fixture')
        shutil.copytree(ROOT / 'ContractFixtures/reference_module/frontend',
                        self.root / 'Sources/ReferenceFixture')
        return self.root / 'Backend/games/reference_fixture/module.json'

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

    def test_root_minimum_macos_copy_is_rejected(self):
        plist = self.root / 'Info.plist'
        data = plistlib.loads(plist.read_bytes())
        data['LSMinimumSystemVersion'] = '14.0'
        plist.write_bytes(plistlib.dumps(data))
        result = run(self.root, 'validate_game_module.py', 'hades2')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('LSMinimumSystemVersion', result.stderr)

    def test_module_without_minimum_macos_is_rejected(self):
        path = self.root / 'Backend/games/hades2/module.json'
        data = json.loads(path.read_text())
        del data['frontend']['minimumMacOS']
        path.write_text(json.dumps(data))
        result = run(self.root, 'validate_game_module.py', 'hades2')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('frontend.minimumMacOS', result.stderr)

    def test_product_without_minimum_macos_is_rejected(self):
        path = self.root / 'app.json'
        data = json.loads(path.read_text())
        del data['minimumMacOS']
        path.write_text(json.dumps(data))
        result = run(self.root, 'product_support.py', 'all')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('minimumMacOS', result.stderr)

    def test_malformed_product_declaration_is_rejected(self):
        (self.root / 'app.json').write_text('{invalid json')
        result = run(self.root, 'validate_game_module.py', 'hades2')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('app.json', result.stderr)
        self.assertIn('valid JSON', result.stderr)

    def test_duplicate_output_identity_is_rejected(self):
        path = self.add_reference_module()
        manifest = json.loads(path.read_text())
        manifest['app']['displayName'] = 'Mac Gaming Trainer'
        path.write_text(json.dumps(manifest))
        result = run(self.root, 'validate_game_module.py', 'reference_fixture')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('displayName', result.stderr)
        self.assertIn('product (app.json)', result.stderr)

    def test_duplicate_bundle_identifier_is_rejected(self):
        path = self.add_reference_module()
        manifest = json.loads(path.read_text())
        for duplicate, owner in (
            (resolved_app(self.root, 'all')['bundleIdentifier'].upper(), 'product (app.json)'),
            (resolved_app(self.root, 'hades2')['bundleIdentifier'].upper(), 'hades2'),
        ):
            with self.subTest(owner=owner):
                manifest['app']['bundleIdentifier'] = duplicate
                path.write_text(json.dumps(manifest))
                result = run(self.root, 'validate_game_module.py', 'reference_fixture')
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('bundleIdentifier', result.stderr)
                self.assertIn(owner, result.stderr)

    def test_module_cannot_claim_product_identity(self):
        path = self.root / 'Backend/games/hades2/module.json'
        manifest = json.loads(path.read_text())
        manifest['app'] = json.loads((self.root / 'app.json').read_text())['app']
        path.write_text(json.dumps(manifest))
        result = run(self.root, 'validate_game_module.py', '--all')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('app.json', result.stderr)
        self.assertIn('hades2', result.stderr)

    def test_isolated_diagnostic_identity_differs_from_product(self):
        product = resolved_app(self.root, 'all')
        diagnostic = resolved_app(self.root, 'hades2')
        self.assertNotEqual(product['displayName'], diagnostic['displayName'])
        self.assertNotEqual(product['bundleIdentifier'], diagnostic['bundleIdentifier'])

    def test_packaged_executable_is_verified_against_root_owner(self):
        manifest = json.loads((self.root / 'Backend/games/hades2/module.json').read_text())
        app_identity = resolved_app(self.root, 'hades2')
        app = self.root / 'dist' / (app_identity['displayName'] + '.app')
        contents = app / 'Contents'
        resources = contents / 'Resources'
        game = resources / 'Backend/games/hades2'
        game.mkdir(parents=True)
        (resources / 'ACTIVE_GAME_ID').write_text('hades2\n')
        (game / 'module.json').write_text(json.dumps(manifest))
        info = plistlib.loads((self.root / 'Info.plist').read_bytes())
        info['CFBundleIdentifier'] = app_identity['bundleIdentifier']
        info['CFBundleName'] = app_identity['displayName']
        info['CFBundleDisplayName'] = app_identity['displayName']
        info['CFBundleExecutable'] = 'WrongExecutable'
        (contents / 'Info.plist').write_bytes(plistlib.dumps(info))
        result = run(self.root, 'verify_module_build.py', 'hades2', '--dist-dir', self.root / 'dist')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('CFBundleExecutable', result.stderr)


if __name__ == '__main__':
    unittest.main()
