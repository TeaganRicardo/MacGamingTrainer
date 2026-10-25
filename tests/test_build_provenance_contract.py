import hashlib
import json
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'Tools/write_build_provenance.py'
VERIFY_SCRIPT = ROOT / 'Tools/verify_build_provenance.py'


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

    def test_ci_macos_provenance_records_exact_host_and_native_toolchain(self):
        actual = git(self.root, 'rev-parse', 'HEAD')
        fake_bin = Path(self.temporary.name) / 'fake-bin'
        fake_bin.mkdir()
        script = fake_bin / 'tool'
        script.write_text("""#!/usr/bin/env python3
import pathlib
import sys

name = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
if name == 'sw_vers':
    values = {'-productVersion': '26.6.2', '-buildVersion': '25G83'}
    print(values[args[0]])
elif name == 'xcode-select':
    print('/Applications/Xcode_26.6.app/Contents/Developer')
elif name == 'xcodebuild':
    print('Xcode 26.6\\nBuild version 17F113')
elif name == 'xcrun':
    values = {
        ('--sdk', 'macosx', '--show-sdk-path'): '/Applications/Xcode_26.6.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX26.5.sdk',
        ('--sdk', 'macosx', '--show-sdk-version'): '26.5',
        ('--sdk', 'macosx', '--show-sdk-build-version'): '25F90',
        ('--find', 'swiftc'): '/Applications/Xcode_26.6.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/swiftc',
        ('swiftc', '--version'): 'Apple Swift version 6.3 (swiftlang-6.3.0.1 clang-1700.4.1.2)',
        ('--find', 'clang'): '/Applications/Xcode_26.6.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/clang',
        ('clang', '--version'): 'Apple clang version 17.0.0 (clang-1700.4.1.2)',
        ('--find', 'lldb'): '/Applications/Xcode_26.6.app/Contents/Developer/usr/bin/lldb',
        ('lldb', '--version'): 'lldb-2600.0.31.7',
        ('lldb', '-P'): '/Applications/Xcode_26.6.app/Contents/SharedFrameworks/LLDB.framework/Resources/Python',
        ('--find', 'python3'): '/Applications/Xcode_26.6.app/Contents/Developer/usr/bin/python3',
        ('python3', '--version'): 'Python 3.9.6',
    }
    print(values[tuple(args)])
else:
    raise SystemExit(f'unexpected fake tool: {name} {args}')
""")
        script.chmod(0o755)
        for name in ('sw_vers', 'xcode-select', 'xcodebuild', 'xcrun'):
            (fake_bin / name).symlink_to(script)
        # The fake tools use /usr/bin/env python3 as their shebang; pin the
        # interpreter so Apple's python3 shim also ignores the fake Xcode path.
        (fake_bin / 'python3').symlink_to(sys.executable)

        # /usr/bin/git on macOS is an xcrun launcher. Resolve the actual Git
        # executable before injecting a simulated, nonexistent DEVELOPER_DIR;
        # source-identity checks must still run against the real repository.
        real_git = (subprocess.check_output(['xcrun', '--find', 'git'], text=True).strip()
                    if sys.platform == 'darwin' else shutil.which('git'))
        self.assertTrue(real_git)
        (fake_bin / 'git').symlink_to(real_git)

        event_path = Path(self.temporary.name) / 'dispatch.json'
        event_path.write_text('{}')
        env = {
            **self.env,
            'PATH': str(fake_bin) + os.pathsep + self.env.get('PATH', ''),
            'GITHUB_EVENT_NAME': 'workflow_dispatch',
            'GITHUB_EVENT_PATH': str(event_path),
            'GITHUB_WORKFLOW': 'Build 2 macOS',
            'GITHUB_REPOSITORY': 'TeaganRicardo/MacGamingTrainer',
            'GITHUB_RUN_ID': '456',
            'GITHUB_RUN_ATTEMPT': '1',
            'GITHUB_RUN_NUMBER': '11',
            'GITHUB_SHA': actual,
            'RUNNER_OS': 'macOS',
            'RUNNER_ARCH': 'ARM64',
            'ImageOS': 'macos26',
            'ImageVersion': '20260907.0351.1',
            'MGT_MACOS_RUNNER_LABEL': 'macos-26',
            'DEVELOPER_DIR': '/Applications/Xcode_26.6.app/Contents/Developer',
        }
        result = self.run_tool(env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads(self.provenance_path().read_text())
        self.assertEqual(manifest['source'], {
            'commit': actual, 'tree': git(self.root, 'rev-parse', 'HEAD^{tree}'),
        })
        self.assertEqual(manifest['toolchain'], {
            'host': {
                'runnerLabel': 'macos-26',
                'runnerOS': 'macOS',
                'runnerArch': 'ARM64',
                'imageOS': 'macos26',
                'imageVersion': '20260907.0351.1',
                'imageMutable': True,
                'macOSVersion': '26.6.2',
                'macOSBuild': '25G83',
            },
            'developer': {
                'requestedDeveloperDir': '/Applications/Xcode_26.6.app/Contents/Developer',
                'selectedDeveloperDir': '/Applications/Xcode_26.6.app/Contents/Developer',
                'xcodeSelectDeveloperDir': '/Applications/Xcode_26.6.app/Contents/Developer',
                'xcodeVersion': '26.6',
                'xcodeBuild': '17F113',
                'sdk': {
                    'name': 'macosx',
                    'path': '/Applications/Xcode_26.6.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX26.5.sdk',
                    'version': '26.5',
                    'build': '25F90',
                },
                'swift': {
                    'path': '/Applications/Xcode_26.6.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/swiftc',
                    'version': 'Apple Swift version 6.3 (swiftlang-6.3.0.1 clang-1700.4.1.2)',
                },
                'clang': {
                    'path': '/Applications/Xcode_26.6.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/clang',
                    'version': 'Apple clang version 17.0.0 (clang-1700.4.1.2)',
                },
                'lldb': {
                    'path': '/Applications/Xcode_26.6.app/Contents/Developer/usr/bin/lldb',
                    'version': 'lldb-2600.0.31.7',
                    'pythonModulePath': '/Applications/Xcode_26.6.app/Contents/SharedFrameworks/LLDB.framework/Resources/Python',
                },
                'xcodePython': {
                    'path': '/Applications/Xcode_26.6.app/Contents/Developer/usr/bin/python3',
                    'version': 'Python 3.9.6',
                },
            },
        })

        missing_image = dict(env)
        missing_image.pop('ImageVersion')
        rejected = self.run_tool(env=missing_image)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn('ImageVersion', rejected.stderr)

    def test_verifier_centralizes_source_module_and_recorded_toolchain_policy(self):
        module = self.root / 'Backend/games/hades2'
        module.mkdir(parents=True)
        module_manifest = module / 'module.json'
        module_manifest.write_text(json.dumps({
            'id': 'hades2', 'displayName': 'Hades II',
            'app': {'displayName': 'Test', 'bundleIdentifier': 'com.example.test'},
        }))
        workflow = self.root / '.github/workflows/build2-macos.yml'
        workflow.parent.mkdir(parents=True)
        workflow.write_text('name: Build 2 macOS\n')
        subprocess.run(['git', 'add', 'Backend', '.github'], cwd=self.root, check=True)
        subprocess.run(['git', 'commit', '-qm', 'module and workflow'], cwd=self.root, check=True)
        actual = git(self.root, 'rev-parse', 'HEAD')
        tree = git(self.root, 'rev-parse', 'HEAD^{tree}')
        provenance = Path(self.temporary.name) / 'fixture.provenance.json'
        toolchain = {
            'host': {
                'runnerLabel': 'macos-26', 'runnerOS': 'macOS', 'runnerArch': 'ARM64',
                'imageOS': 'macos26', 'imageVersion': '20260907.0351.1',
                'imageMutable': True, 'macOSVersion': '26.6.2', 'macOSBuild': '25G83',
            },
            'developer': {
                'requestedDeveloperDir': '/Applications/Xcode_26.6.app/Contents/Developer',
                'selectedDeveloperDir': '/Applications/Xcode_26.6.app/Contents/Developer',
                'xcodeSelectDeveloperDir': '/Applications/Xcode.app/Contents/Developer',
                'xcodeVersion': '26.6', 'xcodeBuild': '17F113',
                'sdk': {'name': 'macosx', 'path': '/SDKs/MacOSX26.5.sdk',
                        'version': '26.5', 'build': '25F90'},
                'swift': {'path': '/toolchain/swiftc', 'version': 'Apple Swift version 6.3'},
                'clang': {'path': '/toolchain/clang', 'version': 'Apple clang version 17.0.0'},
                'lldb': {'path': '/toolchain/lldb', 'version': 'lldb-2600.0.31.7',
                         'pythonModulePath': '/LLDB/Python'},
                'xcodePython': {'path': '/toolchain/python3', 'version': 'Python 3.9.6'},
            },
        }
        manifest = {
            'schemaVersion': 1,
            'productVersion': '0.1.0',
            'bundleBuild': '7',
            'source': {'commit': actual, 'tree': tree},
            'buildInputs': {
                'checkout': 'clean',
                'generatedCopies': [],
                'moduleManifest': {
                    'path': 'Backend/games/hades2/module.json',
                    'sha256': hashlib.sha256(module_manifest.read_bytes()).hexdigest(),
                },
                'workflowSource': {
                    'path': '.github/workflows/build2-macos.yml',
                    'sha256': hashlib.sha256(workflow.read_bytes()).hexdigest(),
                },
            },
            'artifact': {
                'file': self.artifact.name,
                'sha256': hashlib.sha256(self.artifact.read_bytes()).hexdigest(),
            },
            'origin': 'github',
            'workflow': {'name': 'Build 2 macOS', 'eventName': 'workflow_dispatch'},
            'moduleId': 'hades2',
            'toolchain': toolchain,
        }

        def verify(payload):
            provenance.write_text(json.dumps(payload))
            return subprocess.run([
                sys.executable, str(VERIFY_SCRIPT),
                '--provenance', str(provenance),
                '--artifact', str(self.artifact),
                '--repo-root', str(self.root),
                '--expected-source-sha', actual,
                '--module-id', 'hades2',
                '--expected-checkout', 'clean',
                '--expected-generated-copies', '0',
                '--expected-workflow', 'Build 2 macOS',
                '--expected-event', 'workflow_dispatch',
                '--expected-workflow-source', '.github/workflows/build2-macos.yml',
                '--require-macos-toolchain',
            ], cwd=self.root, env=self.env, text=True, capture_output=True)

        valid = verify(manifest)
        self.assertEqual(valid.returncode, 0, valid.stderr)

        wrong_toolchain = json.loads(json.dumps(manifest))
        wrong_toolchain['toolchain']['developer']['xcodeBuild'] = 'wrong'
        rejected = verify(wrong_toolchain)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn('xcodeBuild', rejected.stderr)

        wrong_module = json.loads(json.dumps(manifest))
        wrong_module['buildInputs']['moduleManifest']['sha256'] = 'b' * 64
        rejected = verify(wrong_module)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn('module manifest', rejected.stderr)

        wrong_workflow = json.loads(json.dumps(manifest))
        wrong_workflow['buildInputs']['workflowSource']['sha256'] = 'c' * 64
        rejected = verify(wrong_workflow)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn('workflow source', rejected.stderr)

        wrong_artifact = json.loads(json.dumps(manifest))
        wrong_artifact['artifact']['sha256'] = 'd' * 64
        rejected = verify(wrong_artifact)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn('artifact SHA-256', rejected.stderr)

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

    def test_producer_workflow_source_is_recorded_as_tracked_build_input(self):
        workflow = self.root / '.github/workflows/build2-macos.yml'
        workflow.parent.mkdir(parents=True)
        workflow.write_text('name: Build 2 macOS\n')
        subprocess.run(['git', 'add', '.github'], cwd=self.root, check=True)
        subprocess.run(['git', 'commit', '-qm', 'workflow'], cwd=self.root, check=True)
        self.refresh_artifact_name()

        result = self.run_tool(
            '--local',
            '--workflow-source', '.github/workflows/build2-macos.yml',
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads(self.provenance_path().read_text())
        self.assertEqual(manifest['buildInputs']['workflowSource'], {
            'path': '.github/workflows/build2-macos.yml',
            'sha256': hashlib.sha256(workflow.read_bytes()).hexdigest(),
        })

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
            'release': '20261013',
            'version': '3.15.0',
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
        self.assertEqual(runtime['release'], '20261013')
        self.assertEqual(runtime['version'], '3.15.0')
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

        mismatched = dict(packaged_runtime, version='3.15.1')
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

    def test_unified_product_records_and_verifies_every_module(self):
        product = {
            'schemaVersion': 1,
            'app': {'bundleIdentifier': 'com.example.product', 'displayName': 'Unified'},
            'modules': ['one', 'two'], 'architectures': ['arm64'],
        }
        (self.root / 'app.json').write_text(json.dumps(product))
        for game_id in product['modules']:
            module = self.root / 'Backend/games' / game_id
            module.mkdir(parents=True)
            (module / 'module.json').write_text(json.dumps({'id': game_id, 'displayName': game_id}))
        subprocess.run(['git', 'add', '.'], cwd=self.root, check=True)
        subprocess.run(['git', 'commit', '-qm', 'product modules'], cwd=self.root, check=True)
        self.refresh_artifact_name()
        def package(ids):
            with zipfile.ZipFile(self.artifact, 'w') as archive:
                resources = 'Unified.app/Contents/Resources'
                archive.writestr(resources + '/GAME_MODULES.json', json.dumps(ids))
                archive.writestr('Unified.app/Contents/Info.plist', self.packaged_info('Unified', 'com.example.product'))
                for game_id in ids:
                    archive.writestr(resources + f'/Backend/games/{game_id}/module.json',
                                     (self.root / 'Backend/games' / game_id / 'module.json').read_bytes())
        package(['one', 'two'])
        env = {**self.env, 'GITHUB_EVENT_NAME': 'workflow_dispatch',
               'GITHUB_WORKFLOW': 'Build 2 macOS', 'GITHUB_REPOSITORY': 'example/trainer',
               'GITHUB_RUN_ID': '42', 'GITHUB_RUN_ATTEMPT': '1', 'GITHUB_RUN_NUMBER': '7'}
        result = self.run_tool('--module-id', 'all', env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        provenance = json.loads(self.provenance_path().read_text())
        self.assertEqual(provenance['moduleIds'], ['one', 'two'])
        self.assertEqual([value['path'] for value in provenance['buildInputs']['moduleManifests']],
                         ['Backend/games/one/module.json', 'Backend/games/two/module.json'])
        verify_args = [sys.executable, str(VERIFY_SCRIPT), '--provenance', str(self.provenance_path()),
                       '--artifact', str(self.artifact), '--repo-root', str(self.root),
                       '--expected-source-sha', git(self.root, 'rev-parse', 'HEAD'),
                       '--module-id', 'all', '--expected-checkout', 'clean']
        verified = subprocess.run(verify_args, text=True, capture_output=True)
        self.assertEqual(verified.returncode, 0, verified.stderr)
        second = self.root / 'Backend/games/two/module.json'
        original = second.read_bytes()
        second.write_text('{"id":"two","changed":true}')
        rejected = subprocess.run(verify_args, text=True, capture_output=True)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn('module manifests', rejected.stderr)
        second.write_bytes(original)
        package(['one'])
        missing = self.run_tool('--module-id', 'all', env=env)
        self.assertNotEqual(missing.returncode, 0)
        self.assertIn('module set', missing.stderr)


if __name__ == '__main__':
    program = unittest.main(exit=False)
    if not program.result.wasSuccessful():
        raise SystemExit(1)
    print('build_provenance_contract_ok')
