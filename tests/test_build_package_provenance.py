"""Metadata/package orchestration with temporary apps and external tool doubles.

These are portable provenance tests, not Mach-O build or signing evidence.
The macOS lane verifies the actual compiler, ditto and codesign behavior.
"""
import hashlib
import json
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Tools'))
import write_build_provenance as provenance


class PackageProvenanceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='mgt-package-provenance-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / 'source'
        shutil.copytree(ROOT, self.root, ignore=shutil.ignore_patterns(
            '.git', '__pycache__', 'dist', '.build', 'artifacts'))
        with (self.root / '.gitignore').open('a') as stream:
            stream.write('\nartifacts/\n')
        self.module_path = self.root / 'Backend/games/hades2/module.json'
        self.module = json.loads(self.module_path.read_text())
        self.module['app']['displayName'] = 'Renamed Fixture App'
        self.module_path.write_text(json.dumps(self.module))
        self.git('init', '-q')
        self.git('config', 'user.email', 'test@example.invalid')
        self.git('config', 'user.name', 'Test')
        self.git('add', '.')
        self.git('commit', '-qm', 'fixture')
        self.app = self.root / 'dist/Renamed Fixture App.app'
        self.resources = self.app / 'Contents/Resources'
        self.resources.mkdir(parents=True)
        shutil.copytree(self.root / 'Backend/games/hades2', self.resources / 'Backend/games/hades2')
        (self.resources / 'ACTIVE_GAME_ID').write_text('hades2\n')
        info = plistlib.loads((self.root / 'Info.plist').read_bytes())
        info.update(CFBundleName=self.module['app']['displayName'],
                    CFBundleDisplayName=self.module['app']['displayName'],
                    CFBundleIdentifier=self.module['app']['bundleIdentifier'])
        (self.app / 'Contents/Info.plist').write_bytes(plistlib.dumps(info))
        executable = self.app / 'Contents/MacOS' / info['CFBundleExecutable']
        executable.parent.mkdir()
        executable.write_bytes(b'portable metadata fixture, not a Mach-O binary')
        executable.chmod(0o755)
        for item in self.module.get('appResources', []):
            destination = self.resources / item['destination']
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.root / item['source'], destination)
        tools = Path(temporary.name) / 'external-tools'
        tools.mkdir()
        (tools / 'codesign').write_text('#!' + sys.executable + '\n# External signing double.\n')
        (tools / 'ditto').write_text('#!' + sys.executable + '\n' + '''import pathlib, sys, zipfile
app, artifact = map(pathlib.Path, sys.argv[-2:])
with zipfile.ZipFile(artifact, 'w') as archive:
    for path in app.rglob('*'):
        if path.is_file():
            archive.write(path, path.relative_to(app.parent))
''')
        for tool in tools.iterdir():
            tool.chmod(0o755)
        self.env = {'PATH': str(tools) + os.pathsep + os.environ['PATH']}

    def git(self, *arguments):
        return subprocess.check_output(['git', *arguments], cwd=self.root, text=True).strip()

    def test_package_uses_selected_name_and_computed_resident_hashes(self):
        before = provenance.source_snapshot(self.root, game_id='hades2')
        provenance.seal_build('hades2', self.app, before, self.root)
        result = provenance.package_module('hades2', self.root / 'artifacts', self.root, self.env)
        artifact, sidecar, metadata = (Path(result[key]) for key in ('artifact', 'sidecar', 'provenance'))
        manifest = json.loads(metadata.read_text())
        self.assertEqual(manifest['source']['commit'], self.git('rev-parse', 'HEAD'))
        self.assertEqual(manifest['module']['displayName'], 'Renamed Fixture App')
        self.assertIn('hades2', artifact.name)
        self.assertIn(self.git('rev-parse', 'HEAD')[:8], artifact.name)
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        self.assertEqual(sidecar.read_text(), f'{digest}  {artifact.name}\n')
        resident = manifest['residentRuntime']
        source = self.root / resident['source']
        self.assertEqual(resident['sourceSha256'], hashlib.sha256(source.read_bytes()).hexdigest())
        self.assertEqual(resident['packagedSha256'], resident['sourceSha256'])
        self.assertIsNone(manifest['workflow'])

    def test_changed_source_cannot_be_packaged_as_the_old_build(self):
        before = provenance.source_snapshot(self.root, game_id='hades2')
        provenance.seal_build('hades2', self.app, before, self.root)
        (self.root / 'new-source.txt').write_text('new source\n')
        self.git('add', 'new-source.txt')
        self.git('commit', '-qm', 'source changed after build')
        with self.assertRaisesRegex(RuntimeError, 'source differs'):
            provenance.package_module('hades2', self.root / 'artifacts', self.root, self.env)

    def test_build_rejects_inputs_changed_during_compilation(self):
        before = provenance.source_snapshot(self.root, game_id='hades2')
        (self.root / 'Sources/Unexpected.swift').write_text('struct Unexpected {}\n')
        with self.assertRaisesRegex(RuntimeError, 'inputs changed'):
            provenance.seal_build('hades2', self.app, before, self.root)

    def test_seal_rejects_different_packaged_resident_bytes(self):
        before = provenance.source_snapshot(self.root, game_id='hades2')
        (self.resources / 'Backend/games/hades2/runtime/hades.lua').write_text('different resident')
        with self.assertRaisesRegex(RuntimeError, 'resident bytes differ'):
            provenance.seal_build('hades2', self.app, before, self.root)

    def test_package_cli_emits_owned_output_names(self):
        before = provenance.source_snapshot(self.root, game_id='hades2')
        provenance.seal_build('hades2', self.app, before, self.root)
        github_output = self.root.parent / 'step-output'
        result = subprocess.run([
            sys.executable, str(ROOT / 'Tools/write_build_provenance.py'), '--package', 'hades2',
            '--repo-root', str(self.root), '--output-dir', str(self.root / 'artifacts'),
            '--github-output', str(github_output)], env=self.env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        fields = json.loads(result.stdout)
        self.assertEqual(dict(line.split('=', 1) for line in github_output.read_text().splitlines()), fields)
        for key in ('artifact', 'sidecar', 'provenance'):
            self.assertTrue(Path(fields[key]).is_file())


if __name__ == '__main__':
    unittest.main()
