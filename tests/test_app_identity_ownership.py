"""Selected app identity is explicit and cannot silently shadow its owner."""
import json
import plistlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class AppIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='mgt-app-identity-')
        self.addCleanup(self.temporary.cleanup)
        self.project = Path(self.temporary.name) / 'project'
        shutil.copytree(ROOT, self.project, ignore=shutil.ignore_patterns(
            '.git', '__pycache__', 'dist', '.build', 'artifacts'))

    def validate(self, game_id='hades2'):
        return subprocess.run(
            [sys.executable, str(self.project / 'Tools/validate_game_module.py'), game_id, '--json'],
            text=True, capture_output=True, cwd=self.project,
        )

    def test_root_app_identity_cannot_silently_shadow_module(self):
        path = self.project / 'Info.plist'
        info = plistlib.loads(path.read_bytes())
        info['CFBundleDisplayName'] = 'Shadowed Root Name'
        path.write_bytes(plistlib.dumps(info))
        result = self.validate()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn('CFBundleDisplayName', result.stderr)
        self.assertIn('module', result.stderr)

    def test_root_executable_is_resolved_by_normalized_build_metadata(self):
        path = self.project / 'Info.plist'
        info = plistlib.loads(path.read_bytes())
        info['CFBundleExecutable'] = 'RenamedExecutable'
        path.write_bytes(plistlib.dumps(info))
        result = self.validate()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['app'].get('executable'), 'RenamedExecutable')

    def test_missing_executable_is_not_a_valid_package(self):
        module = json.loads((self.project / 'Backend/games/hades2/module.json').read_text())
        app = self.project / 'dist' / (module['app']['displayName'] + '.app')
        resources = app / 'Contents/Resources'
        packaged_module = resources / 'Backend/games/hades2'
        packaged_module.mkdir(parents=True)
        (packaged_module / 'module.json').write_text(json.dumps(module))
        (resources / 'ACTIVE_GAME_ID').write_text('hades2\n')
        info = plistlib.loads((self.project / 'Info.plist').read_bytes())
        info.update(CFBundleName=module['app']['displayName'],
                    CFBundleDisplayName=module['app']['displayName'],
                    CFBundleIdentifier=module['app']['bundleIdentifier'])
        (app / 'Contents/Info.plist').write_bytes(plistlib.dumps(info))
        result = subprocess.run(
            [sys.executable, str(self.project / 'Tools/verify_module_build.py'), 'hades2',
             '--dist-dir', str(self.project / 'dist')], text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn('executable', result.stderr.lower())

    def test_selected_build_rejects_another_modules_output_name(self):
        fixture = self.project / 'ContractFixtures/reference_module'
        backend = self.project / 'Backend/games/reference_fixture'
        shutil.copytree(fixture / 'backend', backend)
        shutil.copytree(fixture / 'frontend', self.project / 'Sources/ReferenceFixture')
        path = backend / 'module.json'
        manifest = json.loads(path.read_text())
        manifest['app']['displayName'] = 'mac gaming trainer'
        path.write_text(json.dumps(manifest))
        result = self.validate()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn('output', result.stderr.lower())
        self.assertIn('reference_fixture', result.stderr)
        self.assertIn('hades2', result.stderr)


if __name__ == '__main__':
    unittest.main()
