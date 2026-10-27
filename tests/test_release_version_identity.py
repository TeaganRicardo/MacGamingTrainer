"""Release identity must be monotonic across product versions and immutable."""
import plistlib
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Tools"))
from release_tag import published_builds, select_release_tag


def rejects(version, build, history, message):
    try:
        select_release_tag(version, build, history)
    except ValueError as error:
        assert message in str(error), (message, str(error))
    else:
        raise AssertionError(f"accepted invalid release: {version} build {build}")


assert select_release_tag("0.4.0", "7", {"v0.3.0": 6}) == "v0.4.0"
assert select_release_tag("0.3.0", "7", {"v0.3.0": 6}) == "v0.3.0+b7"
assert select_release_tag("0.3.0", "8", {"v0.3.0": 6, "v0.3.0+b7": 7}) == "v0.3.0+b8"
assert select_release_tag("0.1.0", "1", {}) == "v0.1.0"
rejects("0.4.0", "6", {"v0.3.0": 6}, "including across product versions")
rejects("0.3.0", "7", {"v0.3.0": 6, "v0.3.0+b7": 7}, "already exists")
rejects("0.3.0", "8", {"v0.3.0+b7": 7}, "base release tag is missing")
rejects("0.3.0", "7", {"v0.3.0": 6, "v0.4.0": 9}, "including across product versions")
rejects("0.4", "7", {}, "three-part")
rejects("0.4.0", "0", {}, "positive integer")


def git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def tagged_source(repo, version, build, tag):
    (repo / "Info.plist").write_bytes(plistlib.dumps({
        "CFBundleShortVersionString": version,
        "CFBundleVersion": build,
    }))
    git(repo, "add", "Info.plist")
    git(repo, "commit", "-m", f"release {tag}")
    git(repo, "tag", tag)


with tempfile.TemporaryDirectory(prefix="mgt-release-tags-") as tmp:
    repo = Path(tmp)
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "ci@example.invalid")
    git(repo, "config", "user.name", "CI")
    tagged_source(repo, "0.2.0", "4", "v0.2.0")
    tagged_source(repo, "0.3.0", "6", "v0.3.0")
    git(repo, "tag", "v0.1")  # legacy historical form is intentionally ignored
    assert published_builds(repo) == {"v0.2.0": 4, "v0.3.0": 6}
    rejects("0.4.0", "6", published_builds(repo), "including across product versions")
    tagged_source(repo, "0.3.0", "7", "v0.3.0+b7")
    assert published_builds(repo)["v0.3.0+b7"] == 7
    tagged_source(repo, "0.3.0", "8", "v0.3.0+b99")
    try:
        published_builds(repo)
    except ValueError as error:
        assert "source bundle build differs" in str(error)
    else:
        raise AssertionError("malformed release tag was accepted")

workflow = (ROOT / ".github/workflows/direct-release.yml").read_text(encoding="utf-8")
versioning = (ROOT / "VERSIONING.md").read_text(encoding="utf-8")
for required in (
    'python3 Tools/release_tag.py "$version" "$build"',
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
