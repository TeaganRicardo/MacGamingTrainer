import hashlib
import json
import os
import plistlib
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'Tools/write_build_provenance.py'


def git(root, *args):
    return subprocess.check_output(['git', *args], cwd=root, text=True).strip()


class BuildProvenanceContract(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='mgt-provenance-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / 'repo'
        self.root.mkdir()
        subprocess.run(['git', 'init', '-q'], cwd=self.root, check=True)
        subprocess.run(['git', 'config', 'user.email', 'ci@example.invalid'], cwd=self.root, check=True)
        subprocess.run(['git', 'config', 'user.name', 'CI'], cwd=self.root, check=True)
        (self.root / 'source.txt').write_text('source\n')
        (self.root / 'Info.plist').write_bytes(plistlib.dumps({
            'CFBundleExecutable': 'TestTrainer',
            'CFBundleShortVersionString': '0.1.0',
            'CFBundleVersion': '7',
        }))
        subprocess.run(['git', 'add', '.'], cwd=self.root, check=True)
        subprocess.run(['git', 'commit', '-qm', 'base'], cwd=self.root, check=True)
        self.artifact = Path(self.temporary.name) / 'test.zip'
        self.artifact.write_bytes(b'zip fixture')
        self.env = {key: value for key, value in os.environ.items() if not key.startswith('GITHUB_')}

    def run_tool(self, *extra, env=None, version='0.1.0', build='7'):
        return subprocess.run([sys.executable, str(SCRIPT), '--artifact', str(self.artifact),
                               '--product-version', version, '--bundle-build', build,
                               '--repo-root', str(self.root), *extra],
                              cwd=self.root, env=env or self.env, text=True, capture_output=True)

    def test_local_exact_commit_without_github_metadata(self):
        outputs = Path(self.temporary.name) / 'github-output'
        result = self.run_tool('--local', env={**self.env, 'GITHUB_OUTPUT': str(outputs)})
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads((self.artifact.with_name('test.provenance.json')).read_text())
        self.assertEqual(manifest['source']['commit'], git(self.root, 'rev-parse', 'HEAD'))
        self.assertEqual(manifest['source']['tree'], git(self.root, 'rev-parse', 'HEAD^{tree}'))
        self.assertEqual(manifest['artifact']['sha256'], hashlib.sha256(self.artifact.read_bytes()).hexdigest())
        self.assertEqual(manifest['origin'], 'local')
        self.assertNotIn('workflow', manifest)
        self.assertEqual(outputs.read_text().splitlines(), [
            'artifact_name=test.zip',
            'provenance_name=test.provenance.json',
            'sidecar_name=test.zip.sha256',
        ])

    def test_dirty_and_untracked_inputs_refuse_clean_commit_attribution(self):
        (self.root / 'source.txt').write_text('changed\n')
        result = self.run_tool('--local')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('source.txt', result.stderr)
        (self.root / 'source.txt').write_text('source\n')
        (self.root / 'Backend').mkdir()
        (self.root / 'Backend/generated.py').write_text('generated input')
        result = self.run_tool('--local')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Backend/generated.py', result.stderr)

    def test_ci_pr_head_must_be_executed_checkout(self):
        event_path = Path(self.temporary.name) / 'event.json'
        event_path.write_text(json.dumps({
            'number': 199,
            'pull_request': {'head': {'sha': '1' * 40}, 'base': {'sha': '2' * 40}},
        }))
        env = {**self.env, 'GITHUB_EVENT_NAME': 'pull_request',
               'GITHUB_EVENT_PATH': str(event_path), 'GITHUB_WORKFLOW': 'Build 2 macOS',
               'GITHUB_REPOSITORY': 'TeaganRicardo/MacGamingTrainer',
               'GITHUB_RUN_ID': '123', 'GITHUB_RUN_ATTEMPT': '1', 'GITHUB_RUN_NUMBER': '7'}
        result = self.run_tool(env=env)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('head', result.stderr.lower())

    def test_declared_fixture_copy_is_recorded_and_must_match_tracked_source(self):
        source = self.root / 'ContractFixtures/reference_module/backend'
        source.mkdir(parents=True)
        (source / 'module.json').write_text('{"id":"reference_fixture"}\n')
        subprocess.run(['git', 'add', 'ContractFixtures'], cwd=self.root, check=True)
        subprocess.run(['git', 'commit', '-qm', 'fixture'], cwd=self.root, check=True)
        destination = self.root / 'Backend/games/reference_fixture'
        destination.mkdir(parents=True)
        (destination / 'module.json').write_bytes((source / 'module.json').read_bytes())
        declaration = 'ContractFixtures/reference_module/backend:Backend/games/reference_fixture'
        result = self.run_tool('--local', '--generated-copy', declaration)
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads(self.artifact.with_name('test.provenance.json').read_text())
        self.assertEqual(manifest['buildInputs']['checkout'], 'declared-generated')
        self.assertEqual(len(manifest['buildInputs']['generatedCopies']), 1)
        (destination / 'module.json').write_text('changed')
        result = self.run_tool('--local', '--generated-copy', declaration)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('differs', result.stderr)

    def test_resident_hashes_come_from_manifest_and_packaged_bytes(self):
        module = self.root / 'Backend/games/hades2'
        (module / 'runtime').mkdir(parents=True)
        (module / 'module.json').write_text(json.dumps({
            'id': 'hades2',
            'residentRuntime': {'source': 'runtime/hades.lua'},
        }))
        source = module / 'runtime/hades.lua'
        source.write_bytes(b'resident fixture\n')
        subprocess.run(['git', 'add', 'Backend'], cwd=self.root, check=True)
        subprocess.run(['git', 'commit', '-qm', 'resident'], cwd=self.root, check=True)
        packaged = 'Test.app/Contents/Resources/Backend/games/hades2/runtime/hades.lua'
        with zipfile.ZipFile(self.artifact, 'w') as archive:
            archive.writestr('Test.app/Contents/Resources/ACTIVE_GAME_ID', 'hades2\n')
            archive.writestr('Test.app/Contents/Resources/Backend/games/hades2/module.json',
                             (module / 'module.json').read_bytes())
            archive.writestr(packaged, source.read_bytes())
        result = self.run_tool('--local', '--module-id', 'hades2')
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads(self.artifact.with_name('test.provenance.json').read_text())
        expected = hashlib.sha256(source.read_bytes()).hexdigest()
        self.assertEqual(manifest['residentRuntime']['sourceSha256'], expected)
        self.assertEqual(manifest['residentRuntime']['packagedSha256'], expected)
        with zipfile.ZipFile(self.artifact, 'w') as archive:
            archive.writestr('Test.app/Contents/Resources/ACTIVE_GAME_ID', 'hades2\n')
            archive.writestr('Test.app/Contents/Resources/Backend/games/hades2/module.json',
                             (module / 'module.json').read_bytes())
            archive.writestr(packaged, b'wrong bytes')
        result = self.run_tool('--local', '--module-id', 'hades2')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('differs', result.stderr)

    def test_module_id_must_match_packaged_marker_and_manifest(self):
        modules = self.root / 'Backend/games'
        for game_id in ('hades2', 'reference_fixture'):
            module = modules / game_id
            module.mkdir(parents=True)
            (module / 'module.json').write_text(json.dumps({'id': game_id}))
        subprocess.run(['git', 'add', 'Backend'], cwd=self.root, check=True)
        subprocess.run(['git', 'commit', '-qm', 'modules'], cwd=self.root, check=True)

        resources = 'Test.app/Contents/Resources'
        with zipfile.ZipFile(self.artifact, 'w') as archive:
            archive.writestr(f'{resources}/ACTIVE_GAME_ID', 'hades2\n')
            archive.writestr(f'{resources}/Backend/games/hades2/module.json',
                             (modules / 'hades2/module.json').read_bytes())
        mismatch = self.run_tool('--local', '--module-id', 'reference_fixture')
        self.assertNotEqual(mismatch.returncode, 0)
        self.assertIn('module', mismatch.stderr.lower())

        with zipfile.ZipFile(self.artifact, 'w') as archive:
            archive.writestr(f'{resources}/ACTIVE_GAME_ID', 'reference_fixture\n')
            archive.writestr(f'{resources}/Backend/games/reference_fixture/module.json',
                             json.dumps({'id': 'hades2'}))
        wrong_manifest = self.run_tool('--local', '--module-id', 'reference_fixture')
        self.assertNotEqual(wrong_manifest.returncode, 0)
        self.assertIn('manifest', wrong_manifest.stderr.lower())

        with zipfile.ZipFile(self.artifact, 'w') as archive:
            archive.writestr(f'{resources}/ACTIVE_GAME_ID', 'reference_fixture\n')
            archive.writestr(f'{resources}/Backend/games/reference_fixture/module.json',
                             (modules / 'reference_fixture/module.json').read_bytes())
        valid = self.run_tool('--local', '--module-id', 'reference_fixture')
        self.assertEqual(valid.returncode, 0, valid.stderr)
        metadata = json.loads(self.artifact.with_name('test.provenance.json').read_text())
        self.assertEqual(metadata['moduleId'], 'reference_fixture')

    def test_artifact_name_uses_root_executable_and_git_head(self):
        (self.root / 'Info.plist').write_bytes(plistlib.dumps({
            'CFBundleExecutable': 'TestTrainer',
            'CFBundleShortVersionString': '1.2.3',
            'CFBundleVersion': '7',
        }))
        subprocess.run(['git', 'add', 'Info.plist'], cwd=self.root, check=True)
        subprocess.run(['git', 'commit', '-qm', 'identity'], cwd=self.root, check=True)
        result = subprocess.run([
            sys.executable, str(SCRIPT), '--print-artifact-name',
            '--product-version', '1.2.3', '--bundle-build', '7',
            '--repo-root', str(self.root), '--name-label', 'reference_fixture',
        ], cwd=self.root, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(),
                         f'TestTrainer-reference_fixture-1.2.3-b7-{git(self.root, "rev-parse", "HEAD")[:8]}-rc.zip')

    def test_caller_cannot_misstate_plist_product_identity(self):
        for version, build in [('9.9.9', '7'), ('0.1.0', '999')]:
            with self.subTest(version=version, build=build):
                name = subprocess.run([
                    sys.executable, str(SCRIPT), '--print-artifact-name',
                    '--product-version', version, '--bundle-build', build,
                    '--repo-root', str(self.root),
                ], cwd=self.root, text=True, capture_output=True)
                self.assertNotEqual(name.returncode, 0)
                self.assertIn('Info.plist', name.stderr)
                provenance = self.run_tool('--local', version=version, build=build)
                self.assertNotEqual(provenance.returncode, 0)
                self.assertIn('Info.plist', provenance.stderr)


if __name__ == '__main__':
    unittest.main()
