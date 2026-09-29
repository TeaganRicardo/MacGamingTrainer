"""Local source provenance needs no fabricated CI identity."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Tools'))
import write_build_provenance as provenance


class LocalProvenanceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='mgt-local-provenance-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / 'source'
        self.root.mkdir()
        self.artifact = Path(temporary.name) / 'app.zip'
        self.artifact.write_bytes(b'fixture artifact')
        self.git('init', '-q')
        self.git('config', 'user.email', 'test@example.invalid')
        self.git('config', 'user.name', 'Test')
        (self.root / 'source.txt').write_text('original source\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'fixture')

    def git(self, *arguments):
        return subprocess.check_output(['git', *arguments], cwd=self.root, text=True).strip()

    def test_local_metadata_records_actual_source_without_ci_fields(self):
        metadata, checksum, manifest = provenance.write_metadata(
            self.artifact, '1.2.3', '7', self.root, {})
        self.assertEqual(manifest['source']['commit'], self.git('rev-parse', 'HEAD'))
        self.assertEqual(manifest['source']['tree'], self.git('rev-parse', 'HEAD^{tree}'))
        self.assertIsNone(manifest['workflow'])
        self.assertTrue(checksum.is_file())
        self.assertEqual(json.loads(metadata.read_text()), manifest)

    def test_modified_source_cannot_be_attributed_to_clean_commit(self):
        (self.root / 'source.txt').write_text('modified source\n')
        with self.assertRaisesRegex(RuntimeError, 'dirty|untracked'):
            provenance.write_metadata(self.artifact, '1.2.3', '7', self.root, {})

    def test_untracked_build_input_cannot_be_attributed_to_clean_commit(self):
        (self.root / 'extra.py').write_text('unexpected input\n')
        with self.assertRaisesRegex(RuntimeError, 'dirty|untracked'):
            provenance.write_metadata(self.artifact, '1.2.3', '7', self.root, {})

    def test_partial_ci_environment_does_not_fall_back_to_local(self):
        with self.assertRaisesRegex(RuntimeError, 'GITHUB_EVENT_NAME'):
            provenance.write_metadata(self.artifact, '1.2.3', '7', self.root,
                                      {'GITHUB_ACTIONS': 'true'})

    def test_ignored_compiler_input_is_still_detected(self):
        (self.root / '.gitignore').write_text('*.swift\n')
        self.git('add', '.gitignore')
        self.git('commit', '-qm', 'ignore fixture')
        (self.root / 'Sources').mkdir()
        (self.root / 'Sources/Hidden.swift').write_text('struct Hidden {}\n')
        with self.assertRaisesRegex(RuntimeError, 'dirty|untracked'):
            provenance.write_metadata(self.artifact, '1.2.3', '7', self.root, {})

    def test_committed_symlink_cannot_hide_external_build_input(self):
        outside = self.root.parent / 'outside-input'
        outside.write_text('unversioned input')
        (self.root / 'Sources').mkdir()
        (self.root / 'Sources/Linked.swift').symlink_to(outside)
        self.git('add', '.')
        self.git('commit', '-qm', 'link fixture')
        with self.assertRaisesRegex(RuntimeError, 'dirty|untracked|symlink'):
            provenance.write_metadata(self.artifact, '1.2.3', '7', self.root, {})

    def test_declared_generated_inputs_are_verified_and_recorded(self):
        source = self.root / 'ContractFixtures/example'
        source.mkdir(parents=True)
        (source / 'Input.swift').write_text('struct Input {}\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'tracked generation source')
        target = self.root / 'Sources/Generated'
        shutil.copytree(source, target)
        mapping = {'Sources/Generated': 'ContractFixtures/example'}
        _, _, manifest = provenance.write_metadata(
            self.artifact, '1.2.3', '7', self.root, {}, derived_inputs=mapping)
        generated = manifest['buildInputs']['derived']
        self.assertEqual(len(generated), 1)
        self.assertEqual(generated[0]['source'], 'ContractFixtures/example')
        self.assertEqual(generated[0]['destination'], 'Sources/Generated')
        self.assertEqual(len(generated[0]['sha256']), 64)
        (target / 'Input.swift').write_text('struct Altered {}\n')
        with self.assertRaisesRegex(RuntimeError, 'derived|generated'):
            provenance.write_metadata(self.artifact, '1.2.3', '7', self.root, {}, derived_inputs=mapping)


if __name__ == '__main__':
    unittest.main()
