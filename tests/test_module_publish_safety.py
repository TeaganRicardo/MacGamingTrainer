import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Tools'))

import publish_module_build as publisher

with tempfile.TemporaryDirectory(prefix='mgt-module-publish-safety-') as temporary:
    root = Path(temporary)
    staged = root / 'staging/Selected.app'
    staged.mkdir(parents=True)
    (staged / 'Info.plist').write_text('temporary fixture')
    outside = root / 'outside'
    external_app = outside / 'Selected.app'
    external_app.mkdir(parents=True)
    external_marker = external_app / 'keep.txt'
    external_marker.write_text('external app must survive')
    repo = root / 'repo'
    repo.mkdir()
    dist = repo / 'dist'

    dist.symlink_to(outside, target_is_directory=True)
    with patch.object(publisher, '_verify_signature'):
        try:
            publisher.publish_app(staged, dist, 'Selected')
        except (ValueError, OSError):
            pass
        else:
            raise AssertionError('symlinked dist was accepted')
    assert external_marker.read_text() == 'external app must survive'
    dist.unlink()

    dist.mkdir()
    existing_app = dist / 'Selected.app'
    existing_app.mkdir()
    existing_marker = existing_app / 'keep.txt'
    existing_marker.write_text('existing app must survive')
    moved_dist = root / 'moved-dist'
    original_copy = publisher._copy_app

    def swap_dist_after_copy(*args, **kwargs):
        result = original_copy(*args, **kwargs)
        dist.rename(moved_dist)
        dist.symlink_to(outside, target_is_directory=True)
        return result

    with patch.object(publisher, '_verify_signature'), patch.object(publisher, '_copy_app', side_effect=swap_dist_after_copy):
        try:
            publisher.publish_app(staged, dist, 'Selected')
        except (ValueError, OSError):
            pass
        else:
            raise AssertionError('concurrent symlink swap was accepted')
    assert external_marker.read_text() == 'external app must survive'
    assert (moved_dist / 'Selected.app/keep.txt').read_text() == 'existing app must survive'
    dist.unlink()
    moved_dist.rename(dist)
    with patch.object(publisher, '_verify_signature'):
        result = publisher.publish_app(staged, dist, 'Selected')
    assert result == dist / 'Selected.app'
    assert (result / 'Info.plist').read_text() == 'temporary fixture'
    assert not (result / 'keep.txt').exists()
    assert external_marker.read_text() == 'external app must survive'

print('module_publish_safety_ok')
