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
        self.artifact = self.artifact_path()
        self.artifact.write_bytes(b'zip fixture')
        self.env = {key: value for key, value in os.environ.items() if not key.startswith('GITHUB_')}

    def artifact_path(self):
        return Path(self.temporary.name) / f'TestTrainer-0.1.0-b7-{git(self.root, "rev-parse", "HEAD")[:8]}-rc.zip'

    def refresh_artifact_name(self):
        new_path = self.artifact_path()
        self.artifact.rename(new_path)
        self.artifact = new_path

    def provenance_path(self):
        return self.artifact.with_name(f'{self.artifact.stem}.provenance.json')

    def run_tool(self, *extra, env=None, version='0.1.0', build='7'):
        return subprocess.run([sys.executable, str(SCRIPT), '--artifact', str(self.artifact),
                               '--product-version', version, '--bundle-build', build,
                               '--repo-root', str(self.root), *extra],
                              cwd=self.root, env=env or self.env, text=True, capture_output=True)

    def packaged_info(self, name='Test', bundle_id='com.example.test'):
        info = plistlib.loads((self.root / 'Info.plist').read_bytes())
        info.update({'CFBundleName': name, 'CFBundleDisplayName': name,
                     'CFBundleIdentifier': bundle_id})
        return plistlib.dumps(info)

    def test_local_exact_commit_without_github_metadata(self):
        outputs = Path(self.temporary.name) / 'github-output'
        result = self.run_tool('--local', env={**self.env, 'GITHUB_OUTPUT': str(outputs)})
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads(self.provenance_path().read_text())
        self.assertEqual(manifest['source']['commit'], git(self.root, 'rev-parse', 'HEAD'))
        self.assertEqual(manifest['source']['tree'], git(self.root, 'rev-parse', 'HEAD^{tree}'))
        self.assertEqual(manifest['artifact']['sha256'], hashlib.sha256(self.artifact.read_bytes()).hexdigest())
        self.assertEqual(manifest['origin'], 'local')
        self.assertNotIn('workflow', manifest)
        self.assertEqual(outputs.read_text().splitlines(), [
            f'artifact_name={self.artifact.name}',
            f'provenance_name={self.artifact.stem}.provenance.json',
            f'sidecar_name={self.artifact.name}.sha256',
        ])

    def test_writer_rejects_artifact_name_with_false_version(self):
        self.artifact = Path(self.temporary.name) / 'TestTrainer-9.9.9-b999.zip'
        self.artifact.write_bytes(b'zip fixture')
        result = self.run_tool('--local')
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn('artifact name', result.stderr)

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

    def test_ci_pr_metadata_records_exact_checkout(self):
        actual = git(self.root, 'rev-parse', 'HEAD')
        tree = git(self.root, 'rev-parse', 'HEAD^{tree}')
        base = '2' * 40
        event_path = Path(self.temporary.name) / 'event.json'
        event_path.write_text(json.dumps({
            'number': 84,
            'pull_request': {'head': {'sha': actual}, 'base': {'sha': base}},
        }))
        env = {
            **self.env,
            'GITHUB_EVENT_NAME': 'pull_request',
            'GITHUB_EVENT_PATH': str(event_path),
            'GITHUB_WORKFLOW': 'Build 2 macOS',
            'GITHUB_REPOSITORY': 'TeaganRicardo/MacGamingTrainer',
            'GITHUB_RUN_ID': '12345',
            'GITHUB_RUN_ATTEMPT': '2',
            'GITHUB_RUN_NUMBER': '99',
            'GITHUB_SHA': '1' * 40,
        }
        result = self.run_tool(env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads(self.provenance_path().read_text())
        self.assertEqual(manifest['source'], {'commit': actual, 'tree': tree})
        self.assertEqual(manifest['pullRequest'], {
            'number': 84,
            'headSha': actual,
            'baseSha': base,
        })
        self.assertEqual(manifest['workflow'], {
            'eventName': 'pull_request',
            'name': 'Build 2 macOS',
            'repository': 'TeaganRicardo/MacGamingTrainer',
            'runId': '12345',
            'runAttempt': '2',
            'runNumber': '99',
        })
        self.assertEqual(manifest['artifact'], {
            'file': self.artifact.name,
            'sha256': hashlib.sha256(self.artifact.read_bytes()).hexdigest(),
        })
        sidecar = self.artifact.with_name(self.artifact.name + '.sha256')
        self.assertEqual(
            sidecar.read_text(),
            f"{manifest['artifact']['sha256']}  {self.artifact.name}\n",
        )

    def test_workflow_dispatch_does_not_invent_pull_request(self):
        event_path = Path(self.temporary.name) / 'dispatch.json'
        event_path.write_text('{}')
        env = {
            **self.env,
            'GITHUB_EVENT_NAME': 'workflow_dispatch',
            'GITHUB_EVENT_PATH': str(event_path),
            'GITHUB_WORKFLOW': 'Build 2 macOS',
            'GITHUB_REPOSITORY': 'TeaganRicardo/MacGamingTrainer',
            'GITHUB_RUN_ID': '456',
            'GITHUB_RUN_ATTEMPT': '1',
            'GITHUB_RUN_NUMBER': '11',
            'GITHUB_SHA': git(self.root, 'rev-parse', 'HEAD'),
        }
        result = self.run_tool(env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads(self.provenance_path().read_text())
        self.assertNotIn('pullRequest', manifest)
        self.assertEqual(manifest['workflow']['eventName'], 'workflow_dispatch')
        self.assertEqual(manifest['workflow']['runId'], '456')

    def test_declared_fixture_copy_is_recorded_and_must_match_tracked_source(self):
        source = self.root / 'ContractFixtures/reference_module/backend'
        source.mkdir(parents=True)
        (source / 'module.json').write_text('{"id":"reference_fixture"}\n')
        subprocess.run(['git', 'add', 'ContractFixtures'], cwd=self.root, check=True)
        subprocess.run(['git', 'commit', '-qm', 'fixture'], cwd=self.root, check=True)
        self.refresh_artifact_name()
        destination = self.root / 'Backend/games/reference_fixture'
        destination.mkdir(parents=True)
        (destination / 'module.json').write_bytes((source / 'module.json').read_bytes())
        declaration = 'ContractFixtures/reference_module/backend:Backend/games/reference_fixture'
        result = self.run_tool('--local', '--generated-copy', declaration)
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads(self.provenance_path().read_text())
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
            'id': 'hades2', 'displayName': 'Hades II',
            'app': {'displayName': 'Test', 'bundleIdentifier': 'com.example.test'},
            'residentRuntime': {'source': 'runtime/hades.lua'},
        }))
        source = module / 'runtime/hades.lua'
        source.write_bytes(b'resident fixture\n')
        subprocess.run(['git', 'add', 'Backend'], cwd=self.root, check=True)
        subprocess.run(['git', 'commit', '-qm', 'resident'], cwd=self.root, check=True)
        self.refresh_artifact_name()
        packaged = 'Test.app/Contents/Resources/Backend/games/hades2/runtime/hades.lua'
        with zipfile.ZipFile(self.artifact, 'w') as archive:
            archive.writestr('Test.app/Contents/Info.plist', self.packaged_info())
            archive.writestr('Test.app/Contents/MacOS/TestTrainer', b'binary')
            archive.writestr('Test.app/Contents/Resources/ACTIVE_GAME_ID', 'hades2\n')
            archive.writestr('Test.app/Contents/Resources/Backend/games/hades2/module.json',
                             (module / 'module.json').read_bytes())
            archive.writestr(packaged, source.read_bytes())
        result = self.run_tool('--local', '--module-id', 'hades2')
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads(self.provenance_path().read_text())
        expected = hashlib.sha256(source.read_bytes()).hexdigest()
        self.assertEqual(manifest['residentRuntime']['sourceSha256'], expected)
        self.assertEqual(manifest['residentRuntime']['packagedSha256'], expected)
        with zipfile.ZipFile(self.artifact, 'w') as archive:
            archive.writestr('Test.app/Contents/Info.plist', self.packaged_info())
            archive.writestr('Test.app/Contents/MacOS/TestTrainer', b'binary')
            archive.writestr('Test.app/Contents/Resources/ACTIVE_GAME_ID', 'hades2\n')
            archive.writestr('Test.app/Contents/Resources/Backend/games/hades2/module.json',
                             (module / 'module.json').read_bytes())
            archive.writestr(packaged, b'wrong bytes')
        result = self.run_tool('--local', '--module-id', 'hades2')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('differs', result.stderr)

        decoy = packaged.replace('Test.app/', 'Decoy.app/')
        with zipfile.ZipFile(self.artifact, 'w') as archive:
            archive.writestr('Test.app/Contents/Info.plist', self.packaged_info())
            archive.writestr('Test.app/Contents/MacOS/TestTrainer', b'binary')
            archive.writestr('Test.app/Contents/Resources/ACTIVE_GAME_ID', 'hades2\n')
            archive.writestr('Test.app/Contents/Resources/Backend/games/hades2/module.json',
                             (module / 'module.json').read_bytes())
            archive.writestr(decoy, source.read_bytes())
        missing_selected = self.run_tool('--local', '--module-id', 'hades2')
        self.assertNotEqual(missing_selected.returncode, 0)
        self.assertIn('resident', missing_selected.stderr)

        with zipfile.ZipFile(self.artifact, 'a') as archive:
            archive.writestr(packaged, source.read_bytes())
        selected = self.run_tool('--local', '--module-id', 'hades2')
        self.assertEqual(selected.returncode, 0, selected.stderr)
        self.assertEqual(json.loads(self.provenance_path().read_text())['residentRuntime']['packagedPath'],
                         packaged)

    def test_python_runtime_provenance_binds_tracked_declaration_to_package(self):
        module = self.root / 'Backend/games/hades2'
        module.mkdir(parents=True)
        (module / 'module.json').write_text(json.dumps({
            'id': 'hades2', 'displayName': 'Hades II',
            'app': {'displayName': 'Test', 'bundleIdentifier': 'com.example.test'},
        }))
        tools = self.root / 'Tools'
        tools.mkdir()
        source_runtime = {
            'schemaVersion': 1,
            'provider': 'astral-sh/python-build-standalone',
            'release': '20261003',
            'version': '3.15.0rc3',
            'distributions': {
                'arm64': {
                    'target': 'aarch64-apple-darwin',
                    'url': 'https://example.invalid/python-arm64.tar.gz',
                    'sha256': 'a' * 64,
                },
                'x86_64': {
                    'target': 'x86_64-apple-darwin',
                    'url': 'https://example.invalid/python-x86_64.tar.gz',
                    'sha256': 'b' * 64,
                },
            },
        }
        source_path = tools / 'python_runtime.json'
        source_path.write_text(json.dumps(source_runtime, indent=2) + '\n')
        subprocess.run(['git', 'add', 'Backend', 'Tools'], cwd=self.root, check=True)
        subprocess.run(['git', 'commit', '-qm', 'runtime'], cwd=self.root, check=True)
        self.refresh_artifact_name()

        resources = 'Test.app/Contents/Resources'
        packaged_runtime = {
            'schemaVersion': source_runtime['schemaVersion'],
            'provider': source_runtime['provider'],
            'release': source_runtime['release'],
            'version': source_runtime['version'],
            'architectures': ['arm64'],
            'distributions': {
                'arm64': source_runtime['distributions']['arm64'],
            },
        }

        def package(runtime):
            runtime_bytes = (json.dumps(runtime, indent=2, sort_keys=True) + '\n').encode()
            with zipfile.ZipFile(self.artifact, 'w') as archive:
                archive.writestr('Test.app/Contents/Info.plist', self.packaged_info())
                archive.writestr('Test.app/Contents/MacOS/TestTrainer', b'binary')
                archive.writestr(f'{resources}/ACTIVE_GAME_ID', 'hades2\n')
                archive.writestr(
                    f'{resources}/Backend/games/hades2/module.json',
                    (module / 'module.json').read_bytes(),
                )
                archive.writestr(f'{resources}/Python/runtime.json', runtime_bytes)
            return runtime_bytes

        packaged_bytes = package(packaged_runtime)
        result = self.run_tool('--local', '--module-id', 'hades2')
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads(self.provenance_path().read_text())
        runtime = manifest['pythonRuntime']
        self.assertEqual(runtime['provider'], source_runtime['provider'])
        self.assertEqual(runtime['release'], '20261003')
        self.assertEqual(runtime['version'], '3.15.0rc3')
        self.assertEqual(runtime['architectures'], ['arm64'])
        self.assertEqual(
            runtime['distributions'],
            {'arm64': source_runtime['distributions']['arm64']},
        )
        self.assertEqual(
            runtime['sourceSha256'],
            hashlib.sha256(source_path.read_bytes()).hexdigest(),
        )
        self.assertEqual(
            runtime['packagedMetadataSha256'],
            hashlib.sha256(packaged_bytes).hexdigest(),
        )

        mismatched = dict(packaged_runtime, version='3.15.0')
        package(mismatched)
        mismatch = self.run_tool('--local', '--module-id', 'hades2')
        self.assertNotEqual(mismatch.returncode, 0)
        self.assertIn('Python runtime version differs', mismatch.stderr)

        mismatched = dict(packaged_runtime)
        mismatched['distributions'] = {
            'arm64': {**source_runtime['distributions']['arm64'], 'sha256': 'c' * 64},
        }
        package(mismatched)
        mismatch = self.run_tool('--local', '--module-id', 'hades2')
        self.assertNotEqual(mismatch.returncode, 0)
        self.assertIn('Python runtime distributions differ', mismatch.stderr)

    def test_module_id_must_match_packaged_marker_and_manifest(self):
        modules = self.root / 'Backend/games'
        for game_id in ('hades2', 'reference_fixture'):
            module = modules / game_id
            module.mkdir(parents=True)
            (module / 'module.json').write_text(json.dumps({
                'id': game_id, 'displayName': game_id,
                'app': {'displayName': 'Test', 'bundleIdentifier': 'com.example.test'},
            }))
        subprocess.run(['git', 'add', 'Backend'], cwd=self.root, check=True)
        subprocess.run(['git', 'commit', '-qm', 'modules'], cwd=self.root, check=True)
        self.refresh_artifact_name()

        resources = 'Test.app/Contents/Resources'
        with zipfile.ZipFile(self.artifact, 'w') as archive:
            archive.writestr('Test.app/Contents/Info.plist', self.packaged_info())
            archive.writestr('Test.app/Contents/MacOS/TestTrainer', b'binary')
            archive.writestr(f'{resources}/ACTIVE_GAME_ID', 'hades2\n')
            archive.writestr(f'{resources}/Backend/games/hades2/module.json',
                             (modules / 'hades2/module.json').read_bytes())
        mismatch = self.run_tool('--local', '--module-id', 'reference_fixture')
        self.assertNotEqual(mismatch.returncode, 0)
        self.assertIn('module', mismatch.stderr.lower())

        with zipfile.ZipFile(self.artifact, 'w') as archive:
            archive.writestr('Test.app/Contents/Info.plist', self.packaged_info())
            archive.writestr('Test.app/Contents/MacOS/TestTrainer', b'binary')
            archive.writestr(f'{resources}/ACTIVE_GAME_ID', 'reference_fixture\n')
            archive.writestr(f'{resources}/Backend/games/reference_fixture/module.json',
                             json.dumps({'id': 'hades2'}))
        wrong_manifest = self.run_tool('--local', '--module-id', 'reference_fixture')
        self.assertNotEqual(wrong_manifest.returncode, 0)
        self.assertIn('manifest', wrong_manifest.stderr.lower())

        with zipfile.ZipFile(self.artifact, 'w') as archive:
            archive.writestr('Test.app/Contents/Info.plist', self.packaged_info())
            archive.writestr('Test.app/Contents/MacOS/TestTrainer', b'binary')
            archive.writestr(f'{resources}/ACTIVE_GAME_ID', 'reference_fixture\n')
            archive.writestr(f'{resources}/Backend/games/reference_fixture/module.json',
                             (modules / 'reference_fixture/module.json').read_bytes())
        valid = self.run_tool('--local', '--module-id', 'reference_fixture')
        self.assertEqual(valid.returncode, 0, valid.stderr)
        metadata = json.loads(self.provenance_path().read_text())
        self.assertEqual(metadata['moduleId'], 'reference_fixture')

    def test_packaged_app_identity_must_match_source_owners(self):
        module = self.root / 'Backend/games/hades2'
        module.mkdir(parents=True)
        manifest = {
            'id': 'hades2', 'displayName': 'Hades II',
            'app': {'displayName': 'Test App', 'bundleIdentifier': 'com.example.hades2'},
        }
        (module / 'module.json').write_text(json.dumps(manifest))
        subprocess.run(['git', 'add', 'Backend'], cwd=self.root, check=True)
        subprocess.run(['git', 'commit', '-qm', 'module'], cwd=self.root, check=True)
        self.refresh_artifact_name()
        app = 'Test App.app/Contents'
        source_plist = plistlib.loads((self.root / 'Info.plist').read_bytes())
        source_plist.update({
            'CFBundleName': 'Test App', 'CFBundleDisplayName': 'Test App',
            'CFBundleIdentifier': 'com.example.hades2',
        })

        def package(plist):
            with zipfile.ZipFile(self.artifact, 'w') as archive:
                archive.writestr(f'{app}/Info.plist', plistlib.dumps(plist))
                archive.writestr(f'{app}/MacOS/TestTrainer', b'binary')
                archive.writestr(f'{app}/Resources/ACTIVE_GAME_ID', 'hades2\n')
                archive.writestr(f'{app}/Resources/Backend/games/hades2/module.json',
                                 (module / 'module.json').read_bytes())

        for field, wrong in [
            ('CFBundleShortVersionString', '9.9.9'), ('CFBundleVersion', '999'),
            ('CFBundleExecutable', 'WrongExecutable'),
            ('CFBundleIdentifier', 'com.example.wrong'),
            ('CFBundleDisplayName', 'Wrong App'), ('CFBundleName', 'Wrong App'),
        ]:
            with self.subTest(field=field):
                package({**source_plist, field: wrong})
                result = self.run_tool('--local', '--module-id', 'hades2')
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn(field, result.stderr)

        package(source_plist)
        valid = self.run_tool('--local', '--module-id', 'hades2')
        self.assertEqual(valid.returncode, 0, valid.stderr)

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
    program = unittest.main(exit=False)
    if not program.result.wasSuccessful():
        raise SystemExit(1)
    print('build_provenance_contract_ok')
