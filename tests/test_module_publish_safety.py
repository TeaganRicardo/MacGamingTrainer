import json
import plistlib
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Tools'))

import publish_module_build as publisher


def make_identity_app(app, marker, *, bundle_id='com.gao.macgamingtrainer',
                      display_name='Mac Gaming Trainer', modules=('hades2', 'hades')):
    contents = app / 'Contents'
    resources = contents / 'Resources'
    games = resources / 'Backend/games'
    games.mkdir(parents=True)
    (contents / 'Info.plist').write_bytes(plistlib.dumps({
        'CFBundleIdentifier': bundle_id,
        'CFBundleName': display_name,
        'CFBundleDisplayName': display_name,
        'CFBundleExecutable': 'Mac Gaming Trainer',
    }))
    (resources / 'ACTIVE_GAME_ID').write_text(marker + '\n')
    (resources / 'GAME_MODULES.json').write_text(json.dumps(list(modules)))
    for module_id in modules:
        module = games / module_id
        module.mkdir()
        (module / 'module.json').write_text(json.dumps({'id': module_id}))


with tempfile.TemporaryDirectory(prefix='mgt-module-publish-safety-') as temporary:
    root = Path(temporary)
    staged = root / 'staging/Selected.app'
    staged.mkdir(parents=True)
    (staged / 'Info.plist').write_text('temporary fixture')
    staged_marker = staged / 'Contents/Resources/ACTIVE_GAME_ID'
    staged_marker.parent.mkdir(parents=True)
    staged_marker.write_text('selected\n')
    outside = root / 'outside'
    external_app = outside / 'Selected.app'
    external_app.mkdir(parents=True)
    external_marker = external_app / 'keep.txt'
    external_marker.write_text('external app must survive')
    repo = root / 'repo'
    repo.mkdir()
    dist = repo / 'dist'

    dist.symlink_to(outside, target_is_directory=True)
    with patch.object(publisher, 'clean_signing_metadata'), patch.object(publisher, '_verify_signature'):
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
    existing_game = existing_app / 'Contents/Resources/ACTIVE_GAME_ID'
    existing_game.parent.mkdir(parents=True)
    existing_game.write_text('other_module\n')
    with patch.object(publisher, 'clean_signing_metadata'), patch.object(publisher, '_verify_signature'):
        try:
            publisher.publish_app(staged, dist, 'Selected')
        except ValueError as error:
            assert 'other_module' in str(error)
        else:
            raise AssertionError('different module was allowed to replace published app')
    assert existing_marker.read_text() == 'existing app must survive'
    existing_game.write_text('selected\n')
    moved_dist = root / 'moved-dist'
    original_copy = publisher._copy_app

    def swap_dist_after_copy(*args, **kwargs):
        result = original_copy(*args, **kwargs)
        dist.rename(moved_dist)
        dist.symlink_to(outside, target_is_directory=True)
        return result

    with patch.object(publisher, 'clean_signing_metadata'), patch.object(publisher, '_verify_signature'), patch.object(publisher, '_copy_app', side_effect=swap_dist_after_copy):
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
    with patch.object(publisher, 'clean_signing_metadata'), patch.object(publisher, '_verify_signature'):
        result = publisher.publish_app(staged, dist, 'Selected')
    assert result == dist / 'Selected.app'
    assert (result / 'Info.plist').read_text() == 'temporary fixture'
    assert not (result / 'keep.txt').exists()
    assert external_marker.read_text() == 'external app must survive'

# The one supported marker migration is the historical unified product:
# identical product Bundle identity, identical two-module inventory, old marker
# hades2 -> new marker all. Module-only diagnostic output remains isolated.
with tempfile.TemporaryDirectory(prefix='mgt-product-marker-migration-') as temporary:
    root = Path(temporary)
    source = root / 'staging/Mac Gaming Trainer.app'
    legacy = root / 'dist/Mac Gaming Trainer.app'
    source.parent.mkdir()
    legacy.parent.mkdir()
    make_identity_app(source, 'all')
    make_identity_app(legacy, 'hades2')
    with patch.object(publisher, 'clean_signing_metadata'), patch.object(publisher, '_verify_signature'):
        published = publisher.publish_app(source, legacy.parent, 'Mac Gaming Trainer')
        assert published == legacy
        assert publisher._module_id(published) == 'all'
        # A repeated product build is an ordinary same-selection replacement.
        publisher.publish_app(source, legacy.parent, 'Mac Gaming Trainer')
        assert publisher._module_id(legacy) == 'all'

    # A diagnostic Hades II app has a different Bundle identity and only one
    # module; it cannot masquerade as the old unified product during migration.
    diagnostic_dist = root / 'diagnostic-dist'
    diagnostic_dist.mkdir()
    diagnostic = diagnostic_dist / 'Mac Gaming Trainer.app'
    make_identity_app(diagnostic, 'hades2', bundle_id='com.gao.macgamingtrainer.hades2',
                      display_name='Mac Gaming Trainer - Hades II', modules=('hades2',))
    with patch.object(publisher, 'clean_signing_metadata'), patch.object(publisher, '_verify_signature'):
        try:
            publisher.publish_app(source, diagnostic_dist, 'Mac Gaming Trainer')
        except ValueError as error:
            assert 'belongs to hades2' in str(error)
        else:
            raise AssertionError('diagnostic Hades II output was accepted as a legacy unified product')
        assert publisher._module_id(diagnostic) == 'hades2'

    # A product output cannot be replaced by a diagnostic build either.
    diagnostic_source = root / 'staging/Diagnostic.app'
    make_identity_app(diagnostic_source, 'hades2', bundle_id='com.gao.macgamingtrainer.hades2',
                      display_name='Mac Gaming Trainer - Hades II', modules=('hades2',))
    with patch.object(publisher, 'clean_signing_metadata'), patch.object(publisher, '_verify_signature'):
        try:
            publisher.publish_app(diagnostic_source, legacy.parent, 'Mac Gaming Trainer')
        except ValueError as error:
            assert 'belongs to all' in str(error)
        else:
            raise AssertionError('diagnostic build replaced the unified product')
        assert publisher._module_id(legacy) == 'all'

print('module_publish_safety_ok')
