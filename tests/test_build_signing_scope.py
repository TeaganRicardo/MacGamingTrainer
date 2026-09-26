import os
import subprocess
import tempfile
from pathlib import Path

from sys import path as sys_path

TOOLS = Path(__file__).resolve().parents[1] / 'Tools'
sys_path.insert(0, str(TOOLS))
from clean_signing_metadata import clean_signing_metadata

with tempfile.TemporaryDirectory(prefix='mgt-signing-scope-') as temporary:
    root = Path(temporary)
    stage = root / 'staging'
    stage.mkdir()
    app = stage / 'Selected.app'
    app.mkdir()
    outside = root / 'Outside.app'
    outside.mkdir()
    nested = stage / 'nested' / 'Nested.app'
    nested.parent.mkdir()
    nested.mkdir()
    source = root / 'source.txt'
    source.write_text('do not modify this source')
    linked_app = stage / 'Linked.app'
    linked_app.symlink_to(outside, target_is_directory=True)
    linked_stage = root / 'linked-staging'
    linked_stage.symlink_to(stage, target_is_directory=True)

    for target, allowed_root in (
        (source, root),
        (outside, stage),
        (nested, stage),
        (linked_app, stage),
        (linked_stage / app.name, linked_stage),
    ):
        try:
            clean_signing_metadata(target, allowed_root)
        except ValueError:
            pass
        else:
            raise AssertionError(f'cleanup accepted a non-staged app: {target}')
    assert source.read_text() == 'do not modify this source'

build = (TOOLS.parent / 'build.sh').read_text(encoding='utf-8')
publish_guard = next(
    line for line in build.splitlines() if line.startswith('[[ ! -L "$PUBLISH_DIST" ]]')
)
with tempfile.TemporaryDirectory(prefix='mgt-publish-symlink-') as temporary:
    root = Path(temporary)
    outside = root / 'outside'
    saved_app = outside / 'Existing.app'
    saved_app.mkdir(parents=True)
    sentinel = saved_app / 'keep.txt'
    sentinel.write_text('preserved')
    link = root / 'dist'
    link.symlink_to(outside, target_is_directory=True)
    result = subprocess.run(
        ['bash', '-c', publish_guard],
        env={**os.environ, 'PUBLISH_DIST': str(link)},
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert sentinel.read_text() == 'preserved'

print('build_signing_scope_ok')
