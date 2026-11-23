"""Release identity must be monotonic across product versions and immutable."""
import plistlib
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Tools"))
from release_tag import published_builds, release_identity_changed, select_release_tag


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

    # Root commit with no readable Info.plist parent must fail closed (need release).
    (repo / "Info.plist").write_bytes(plistlib.dumps({
        "CFBundleShortVersionString": "0.3.1",
        "CFBundleVersion": "9",
        "CFBundleName": "Initial",
    }))
    git(repo, "add", "Info.plist")
    git(repo, "commit", "-m", "non-version metadata prep")
    v9_sha = git(repo, "rev-parse", "HEAD").stdout.decode().strip()
    assert release_identity_changed(repo, "0" * 40, v9_sha) is True

    # Non-version Info.plist edits on main must skip release precheck cleanly.
    (repo / "Info.plist").write_bytes(plistlib.dumps({
        "CFBundleShortVersionString": "0.3.1",
        "CFBundleVersion": "9",
        "CFBundleName": "MetadataOnly",
    }))
    git(repo, "add", "Info.plist")
    git(repo, "commit", "-m", "metadata only")
    meta_sha = git(repo, "rev-parse", "HEAD").stdout.decode().strip()
    assert release_identity_changed(repo, v9_sha, meta_sha) is False
    assert release_identity_changed(repo, "0" * 40, meta_sha) is False

    # Version or build bumps trigger release validation.
    (repo / "Info.plist").write_bytes(plistlib.dumps({
        "CFBundleShortVersionString": "0.3.1",
        "CFBundleVersion": "10",
        "CFBundleName": "MetadataOnly",
    }))
    git(repo, "add", "Info.plist")
    git(repo, "commit", "-m", "bump build")
    b10_sha = git(repo, "rev-parse", "HEAD").stdout.decode().strip()
    assert release_identity_changed(repo, meta_sha, b10_sha) is True
    unchanged_cli = subprocess.run(
        [sys.executable, str(ROOT / "Tools/release_tag.py"), "--repo-root", str(repo), "--push-precheck", v9_sha, meta_sha],
        check=True, capture_output=True, text=True,
    )
    assert unchanged_cli.stdout.strip() == "false", unchanged_cli.stdout
    changed_cli = subprocess.run(
        [sys.executable, str(ROOT / "Tools/release_tag.py"), "--repo-root", str(repo), "--push-precheck", meta_sha, b10_sha],
        check=True, capture_output=True, text=True,
    )
    assert changed_cli.stdout.strip() == "true", changed_cli.stdout

    # Version-only bumps and backwards build reverts must trigger release validation.
    (repo / "Info.plist").write_bytes(plistlib.dumps({
        "CFBundleShortVersionString": "0.4.0",
        "CFBundleVersion": "10",
    }))
    git(repo, "add", "Info.plist")
    git(repo, "commit", "-m", "bump marketing version")
    v40_sha = git(repo, "rev-parse", "HEAD").stdout.decode().strip()
    assert release_identity_changed(repo, b10_sha, v40_sha) is True

    (repo / "Info.plist").write_bytes(plistlib.dumps({
        "CFBundleShortVersionString": "0.4.0",
        "CFBundleVersion": "9",
    }))
    git(repo, "add", "Info.plist")
    git(repo, "commit", "-m", "revert build")
    revert_sha = git(repo, "rev-parse", "HEAD").stdout.decode().strip()
    assert release_identity_changed(repo, v40_sha, revert_sha) is True

    # Non-dict or malformed plists fail closed: base corruption still requests release,
    # while corrupt HEAD rejects precheck with exit code 2.
    (repo / "Info.plist").write_bytes(plistlib.dumps(["not", "a", "dict"]))
    git(repo, "add", "Info.plist")
    git(repo, "commit", "-m", "non-dict plist")
    array_sha = git(repo, "rev-parse", "HEAD").stdout.decode().strip()
    bad_head = subprocess.run(
        [sys.executable, str(ROOT / "Tools/release_tag.py"), "--repo-root", str(repo), "--push-precheck", revert_sha, array_sha],
        capture_output=True, text=True,
    )
    assert bad_head.returncode == 2, (bad_head.returncode, bad_head.stderr)

    (repo / "Info.plist").write_bytes(plistlib.dumps({
        "CFBundleShortVersionString": "0.4.0",
        "CFBundleVersion": "11",
    }))
    git(repo, "add", "Info.plist")
    git(repo, "commit", "-m", "recover valid plist")
    recovered_sha = git(repo, "rev-parse", "HEAD").stdout.decode().strip()
    assert release_identity_changed(repo, array_sha, recovered_sha) is True

print("release_version_identity_ok")
