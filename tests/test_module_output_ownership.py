"""A verified build must not overwrite an app owned by another module."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Tools'))
import publish_module_build as publisher


class PublicationOwnershipTests(unittest.TestCase):
    def test_foreign_module_survives_same_destination(self):
        with tempfile.TemporaryDirectory(prefix='mgt-publish-owner-') as temporary:
            root = Path(temporary)
            source = root / 'staging/Shared.app'
            destination = root / 'dist/Shared.app'
            for app, module in ((source, 'selected_module'), (destination, 'other_module')):
                resources = app / 'Contents/Resources'
                resources.mkdir(parents=True)
                (resources / 'ACTIVE_GAME_ID').write_text(module + '\n')
            marker = destination / 'must-survive'
            marker.write_text('owned by another module')
            with patch.object(publisher, '_verify_signature'):
                with self.assertRaisesRegex(ValueError, 'module'):
                    publisher.publish_app(source, root / 'dist', 'Shared')
            self.assertEqual(marker.read_text(), 'owned by another module')
            self.assertEqual((destination / 'Contents/Resources/ACTIVE_GAME_ID').read_text(), 'other_module\n')


if __name__ == '__main__':
    unittest.main()
