import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "Tools/write_build_provenance.py"


def run(*args, cwd: Path, env=None):
    return subprocess.run(args, cwd=cwd, check=True, text=True, env=env)


def output(*args, cwd: Path) -> str:
    return subprocess.check_output(args, cwd=cwd, text=True).strip()


with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp) / "repo"
    root.mkdir()
    run("git", "init", "-q", cwd=root)
    run("git", "config", "user.email", "ci@example.invalid", cwd=root)
    run("git", "config", "user.name", "CI", cwd=root)
    (root / "source.txt").write_text("source\n", encoding="utf-8")
    run("git", "add", ".", cwd=root)
    run("git", "commit", "-qm", "base", cwd=root)

    actual_commit = output("git", "rev-parse", "HEAD", cwd=root)
    actual_tree = output("git", "rev-parse", "HEAD^{tree}", cwd=root)
    fake_head = "1" * 40
    fake_base = "2" * 40
    assert actual_commit != fake_head

    artifacts = Path(tmp) / "artifacts"
    artifacts.mkdir()
    artifact = artifacts / "MacGamingTrainer-test.zip"
    artifact.write_bytes(b"zip bytes for provenance test")

    event_path = Path(tmp) / "event.json"
    event_path.write_text(json.dumps({
        "number": 84,
        "pull_request": {
            "head": {"sha": fake_head},
            "base": {"sha": fake_base},
        },
    }), encoding="utf-8")

    env = {
        **os.environ,
        "GITHUB_EVENT_NAME": "pull_request",
        "GITHUB_EVENT_PATH": str(event_path),
        "GITHUB_WORKFLOW": "Build 2 macOS",
        "GITHUB_REPOSITORY": "TeaganRicardo/MacGamingTrainer",
        "GITHUB_RUN_ID": "12345",
        "GITHUB_RUN_ATTEMPT": "2",
        "GITHUB_RUN_NUMBER": "99",
        # Deliberately misleading; source identity must still come from git checkout.
        "GITHUB_SHA": fake_head,
    }
    mismatched = subprocess.run([
        sys.executable,
        str(SCRIPT),
        "--artifact", str(artifact),
        "--product-version", "0.1.0",
        "--bundle-build", "7",
        "--repo-root", str(root),
    ], cwd=root, env=env, text=True, capture_output=True)
    assert mismatched.returncode != 0
    assert "head" in mismatched.stderr.lower()

    # CI provenance is recorded only for an executable checkout of the PR head.
    payload = json.loads(event_path.read_text(encoding="utf-8"))
    payload["pull_request"]["head"]["sha"] = actual_commit
    event_path.write_text(json.dumps(payload), encoding="utf-8")
    run(
        sys.executable, str(SCRIPT),
        "--artifact", str(artifact),
        "--product-version", "0.1.0",
        "--bundle-build", "7",
        "--repo-root", str(root),
        cwd=root, env=env,
    )

    provenance = artifacts / "MacGamingTrainer-test.provenance.json"
    sidecar = artifacts / "MacGamingTrainer-test.zip.sha256"
    manifest = json.loads(provenance.read_text(encoding="utf-8"))
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()

    assert manifest["source"] == {"commit": actual_commit, "tree": actual_tree}
    assert manifest["pullRequest"] == {
        "number": 84,
        "headSha": actual_commit,
        "baseSha": fake_base,
    }
    assert manifest["workflow"] == {
        "eventName": "pull_request",
        "name": "Build 2 macOS",
        "repository": "TeaganRicardo/MacGamingTrainer",
        "runId": "12345",
        "runAttempt": "2",
        "runNumber": "99",
    }
    assert manifest["artifact"] == {
        "file": artifact.name,
        "sha256": digest,
    }
    assert sidecar.read_text(encoding="utf-8") == f"{digest}  {artifact.name}\n"

    # Non-PR builds must not invent pull-request metadata.
    push_artifact = artifacts / "MacGamingTrainer-push.zip"
    push_artifact.write_bytes(b"push build")
    push_env = {
        **env,
        "GITHUB_EVENT_NAME": "push",
        "GITHUB_SHA": actual_commit,
    }
    run(
        sys.executable,
        str(SCRIPT),
        "--artifact", str(push_artifact),
        "--product-version", "0.1.0",
        "--bundle-build", "7",
        "--repo-root", str(root),
        cwd=root,
        env=push_env,
    )
    push_manifest = json.loads(
        (artifacts / "MacGamingTrainer-push.provenance.json").read_text(encoding="utf-8")
    )
    assert "pullRequest" not in push_manifest

print("build_artifact_provenance_ok")
