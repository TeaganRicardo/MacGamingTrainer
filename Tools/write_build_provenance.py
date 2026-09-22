#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Mapping


def git_value(repo_root: Path, revision: str) -> str:
    return subprocess.check_output(
        ["git", "rev-parse", revision], cwd=repo_root, text=True
    ).strip()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_env(env: Mapping[str, str], name: str) -> str:
    value = env.get(name, "").strip()
    if not value:
        raise RuntimeError(f"missing required environment variable: {name}")
    return value


def build_manifest(
    artifact: Path,
    product_version: str,
    bundle_build: str,
    repo_root: Path,
    env: Mapping[str, str],
) -> dict[str, object]:
    source_sha = git_value(repo_root, "HEAD")
    source_tree = git_value(repo_root, "HEAD^{tree}")
    digest = sha256_file(artifact)
    event_name = require_env(env, "GITHUB_EVENT_NAME")

    manifest: dict[str, object] = {
        "schemaVersion": 1,
        "productVersion": product_version,
        "bundleBuild": bundle_build,
        "source": {
            "commit": source_sha,
            "tree": source_tree,
        },
        "workflow": {
            "eventName": event_name,
            "name": require_env(env, "GITHUB_WORKFLOW"),
            "repository": require_env(env, "GITHUB_REPOSITORY"),
            "runId": require_env(env, "GITHUB_RUN_ID"),
            "runAttempt": require_env(env, "GITHUB_RUN_ATTEMPT"),
            "runNumber": require_env(env, "GITHUB_RUN_NUMBER"),
        },
        "artifact": {
            "file": artifact.name,
            "sha256": digest,
        },
    }

    if event_name == "pull_request":
        event_path = Path(require_env(env, "GITHUB_EVENT_PATH"))
        payload = json.loads(event_path.read_text(encoding="utf-8"))
        pull_request = payload.get("pull_request")
        if not isinstance(pull_request, dict):
            raise RuntimeError("pull_request event is missing pull_request metadata")
        head = pull_request.get("head")
        base = pull_request.get("base")
        if not isinstance(head, dict) or not isinstance(base, dict):
            raise RuntimeError("pull_request event is missing head/base metadata")
        manifest["pullRequest"] = {
            "number": payload.get("number"),
            "headSha": head.get("sha"),
            "baseSha": base.get("sha"),
        }

    return manifest


def write_metadata(
    artifact: Path,
    product_version: str,
    bundle_build: str,
    repo_root: Path,
    env: Mapping[str, str],
) -> tuple[Path, Path, dict[str, object]]:
    manifest = build_manifest(artifact, product_version, bundle_build, repo_root, env)
    sidecar = artifact.with_name(f"{artifact.name}.sha256")
    provenance = artifact.with_name(f"{artifact.stem}.provenance.json")

    artifact_metadata = manifest["artifact"]
    if not isinstance(artifact_metadata, dict):
        raise RuntimeError("invalid artifact metadata")
    digest = artifact_metadata["sha256"]
    sidecar.write_text(f"{digest}  {artifact.name}\n", encoding="utf-8")
    provenance.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return provenance, sidecar, manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--product-version", required=True)
    parser.add_argument("--bundle-build", required=True)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    args = parser.parse_args()

    artifact = args.artifact.resolve()
    repo_root = args.repo_root.resolve()
    if not artifact.is_file():
        raise SystemExit(f"artifact does not exist: {artifact}")

    provenance, sidecar, manifest = write_metadata(
        artifact,
        args.product_version,
        args.bundle_build,
        repo_root,
        os.environ,
    )
    source = manifest["source"]
    if not isinstance(source, dict):
        raise RuntimeError("invalid source metadata")
    print(f"source_sha={source['commit']}")
    print(f"source_tree={source['tree']}")
    print(f"provenance={provenance}")
    print(f"sidecar={sidecar}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
