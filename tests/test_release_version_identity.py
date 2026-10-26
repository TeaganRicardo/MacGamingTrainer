"""Release-tag policy is immutable and supports new builds of the same SemVer."""
import plistlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
source = plistlib.loads((ROOT / "Info.plist").read_bytes())
assert "." in source["CFBundleShortVersionString"]
assert int(source["CFBundleVersion"]) >= 1

workflow = (ROOT / ".github/workflows/direct-release.yml").read_text(encoding="utf-8")
versioning = (ROOT / "VERSIONING.md").read_text(encoding="utf-8")
for required in (
    'base_tag="v$version"',
    'tag="$base_tag"',
    'git show "$base_tag:Info.plist"',
    'git tag -l "${base_tag}+b*"',
    'tag="${base_tag}+b${build}"',
    'build <= previous_build',
    'git rev-parse -q --verify "refs/tags/$tag"',
    '--target "$GITHUB_SHA"',
    '--notes-file "$RUNNER_TEMP/release-notes.md"',
    'Verify retained artifact provenance and checksum',
):
    assert required in workflow, required
assert "gh release create" in workflow
assert "gh release edit" not in workflow
assert 'vMAJOR.MINOR.PATCH+bBUILD' in versioning
assert "Current product version:" not in versioning

print("release_version_identity_ok")
