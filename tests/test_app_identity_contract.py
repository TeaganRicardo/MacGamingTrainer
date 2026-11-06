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
    """App identity as the build owner resolves it for a product or module selection."""
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
                self.assertIn('app.json', result.stderr)

    def test_duplicate_bundle_identifier_is_rejected(self):
        shutil.copytree(ROOT / 'ContractFixtures/reference_module/backend',
                        self.root / 'Backend/games/reference_fixture')
        shutil.copytree(ROOT / 'ContractFixtures/reference_module/frontend',
                        self.root / 'Sources/ReferenceFixture')
        path = self.root / 'Backend/games/reference_fixture/module.json'
        manifest = json.loads(path.read_text())
        for duplicate, owner in (('COM.GAO.MACGAMINGTRAINER', 'app.json'),
                                 (resolved_app(self.root, 'hades2')['bundleIdentifier'].upper(), 'hades2')):
            with self.subTest(duplicate=duplicate):
                manifest['app']['bundleIdentifier'] = duplicate
                path.write_text(json.dumps(manifest))
                result = run(self.root, 'validate_game_module.py', 'reference_fixture')
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('bundleIdentifier', result.stderr)
                self.assertIn(owner, result.stderr)

    def test_module_cannot_claim_product_identity(self):
        # An isolated diagnostic App that reuses the product identity would be
        # published over the product and share its preferences and target lease.
        product = json.loads((self.root / 'app.json').read_text())['app']
        path = self.root / 'Backend/games/hades2/module.json'
        manifest = json.loads(path.read_text())
        manifest['app'] = dict(product)
        path.write_text(json.dumps(manifest))
        result = run(self.root, 'validate_game_module.py', '--all')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('app.json', result.stderr)
        self.assertIn('hades2', result.stderr)

    def test_isolated_diagnostic_identities_differ_from_product(self):
        product = resolved_app(self.root, 'all')
        modules = json.loads((self.root / 'app.json').read_text())['modules']
        for game_id in modules:
            with self.subTest(game_id=game_id):
                diagnostic = resolved_app(self.root, game_id)
                for field in ('displayName', 'bundleIdentifier'):
                    self.assertNotEqual(diagnostic[field].casefold(), product[field].casefold())

    def test_packaged_executable_is_verified_against_root_owner(self):
        manifest = json.loads((self.root / 'Backend/games/hades2/module.json').read_text())
        identity = resolved_app(self.root, 'hades2')
        app = self.root / 'dist' / (identity['displayName'] + '.app')
        contents = app / 'Contents'
        resources = contents / 'Resources'
        game = resources / 'Backend/games/hades2'
        game.mkdir(parents=True)
        (resources / 'ACTIVE_GAME_ID').write_text('hades2\n')
        (game / 'module.json').write_text(json.dumps(manifest))
        info = plistlib.loads((self.root / 'Info.plist').read_bytes())
        info['CFBundleIdentifier'] = identity['bundleIdentifier']
        info['CFBundleName'] = identity['displayName']
        info['CFBundleDisplayName'] = identity['displayName']
        (contents / 'Info.plist').write_bytes(plistlib.dumps(info))
        result = run(self.root, 'verify_module_build.py', 'hades2', '--dist-dir', self.root / 'dist')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('executable', result.stderr.lower())


if __name__ == '__main__':
    unittest.main()
