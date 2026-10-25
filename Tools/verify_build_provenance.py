#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from macos_toolchain_identity import (
    collect_macos_toolchain,
    verify_recorded_macos_toolchain,
)
from write_build_provenance import git_value, require_product_identity, sha256_file, product_module_ids


def require_object(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise RuntimeError(f"{name} must be an object")
    return value


def verify_provenance(
    provenance: Path,
    repo_root: Path,
    *,
    expected_source_sha: str,
    module_id: str,
    artifact_path: Path | None = None,
    expected_checkout: str,
    expected_generated_copies: int | None = None,
    expected_workflow: str = "",
    expected_event: str = "",
    expected_workflow_source: str = "",
    require_macos_toolchain: bool = False,
    match_current_macos_toolchain: bool = False,
) -> dict[str, object]:
    if not re.fullmatch(r"[0-9a-f]{40}", expected_source_sha):
        raise RuntimeError("expected source SHA must be a full lowercase Git commit SHA")
    if expected_checkout not in ("clean", "declared-generated"):
        raise RuntimeError(f"unsupported expected checkout identity: {expected_checkout!r}")
    if expected_generated_copies is not None and expected_generated_copies < 0:
        raise RuntimeError("expected generated-copy count cannot be negative")

    repo_root = repo_root.resolve()
    manifest = require_object(json.loads(provenance.read_text(encoding="utf-8")), "provenance")
    if manifest.get("schemaVersion") != 1:
        raise RuntimeError("unsupported provenance schemaVersion")

    product_version = manifest.get("productVersion")
    bundle_build = manifest.get("bundleBuild")
    if not isinstance(product_version, str) or not isinstance(bundle_build, str):
        raise RuntimeError("provenance product identity is invalid")
    require_product_identity(repo_root, product_version, bundle_build)

    source = require_object(manifest.get("source"), "provenance source")
    expected_tree = git_value(repo_root, f"{expected_source_sha}^{{tree}}")
    if source != {"commit": expected_source_sha, "tree": expected_tree}:
        raise RuntimeError("provenance source commit/tree differs from expected source")

    build_inputs = require_object(manifest.get("buildInputs"), "provenance buildInputs")
    if build_inputs.get("checkout") != expected_checkout:
        raise RuntimeError("provenance checkout identity differs from expected build inputs")
    generated = build_inputs.get("generatedCopies")
    if not isinstance(generated, list):
        raise RuntimeError("provenance generatedCopies must be an array")
    if expected_generated_copies is not None and len(generated) != expected_generated_copies:
        raise RuntimeError("provenance generated-copy count differs from expected build inputs")

    if expected_workflow_source:
        workflow_path = Path(expected_workflow_source)
        if workflow_path.is_absolute() or not workflow_path.parts or ".." in workflow_path.parts:
            raise RuntimeError("expected workflow source must stay inside the repository")
        workflow_file = (repo_root / workflow_path).resolve()
        if repo_root not in workflow_file.parents or not workflow_file.is_file():
            raise RuntimeError("expected workflow source is missing")
        expected_workflow_input = {
            "path": workflow_path.as_posix(),
            "sha256": sha256_file(workflow_file),
        }
        if build_inputs.get("workflowSource") != expected_workflow_input:
            raise RuntimeError("provenance workflow source differs from current source")

    if manifest.get("origin") != "github":
        raise RuntimeError("release/QA provenance must originate from GitHub")

    workflow = require_object(manifest.get("workflow"), "provenance workflow")
    if expected_workflow and workflow.get("name") != expected_workflow:
        raise RuntimeError("provenance workflow name differs from expected producer")
    if expected_event and workflow.get("eventName") != expected_event:
        raise RuntimeError("provenance workflow event differs from expected producer")

    if manifest.get("moduleId") != module_id:
        raise RuntimeError("provenance module ID differs from expected module")
    if module_id == 'all':
        ids = product_module_ids(repo_root)
        if manifest.get('moduleIds') != list(ids):
            raise RuntimeError('provenance module set differs from app.json')
        expected_product = {'path': 'app.json', 'sha256': sha256_file(repo_root / 'app.json')}
        if build_inputs.get('productManifest') != expected_product:
            raise RuntimeError('provenance product manifest differs from current source')
        expected_modules = [
            {'path': f'Backend/games/{game_id}/module.json',
             'sha256': sha256_file(repo_root / 'Backend/games' / game_id / 'module.json')}
            for game_id in ids
        ]
        if build_inputs.get('moduleManifests') != expected_modules:
            raise RuntimeError('provenance module manifests differ from current source')
    else:
        module_manifest = repo_root / "Backend" / "games" / module_id / "module.json"
        module_input = require_object(build_inputs.get("moduleManifest"), "provenance moduleManifest")
        expected_module_input = {
            "path": module_manifest.relative_to(repo_root).as_posix(),
            "sha256": sha256_file(module_manifest),
        }
        if module_input != expected_module_input:
            raise RuntimeError("provenance module manifest differs from current source")

    python_runtime = manifest.get("pythonRuntime")
    runtime_declaration = repo_root / "Tools" / "python_runtime.json"
    if python_runtime is not None:
        runtime = require_object(python_runtime, "provenance pythonRuntime")
        if runtime.get("sourceSha256") != sha256_file(runtime_declaration):
            raise RuntimeError("provenance Python runtime declaration differs from current source")

    if module_id == 'all':
        runtimes = require_object(manifest.get('residentRuntimes'), 'provenance residentRuntimes')
        if set(runtimes) - set(ids):
            raise RuntimeError('provenance resident runtime has an undeclared module')
        resident_values = list(runtimes.values())
    else:
        resident_values = [manifest['residentRuntime']] if 'residentRuntime' in manifest else []
    for resident_runtime in resident_values:
        resident = require_object(resident_runtime, "provenance residentRuntime")
        source_path = resident.get("source")
        if not isinstance(source_path, str) or not source_path:
            raise RuntimeError("provenance resident runtime source is missing")
        current_source = (repo_root / source_path).resolve()
        if repo_root not in current_source.parents or not current_source.is_file():
            raise RuntimeError("provenance resident runtime source is invalid")
        source_digest = sha256_file(current_source)
        if resident.get("sourceSha256") != source_digest:
            raise RuntimeError("provenance resident runtime differs from current source")
        if resident.get("packagedSha256") != source_digest:
            raise RuntimeError("provenance packaged resident runtime differs from current source")

    toolchain = manifest.get("toolchain")
    if require_macos_toolchain or match_current_macos_toolchain:
        verify_recorded_macos_toolchain(toolchain)
    elif toolchain is not None:
        verify_recorded_macos_toolchain(toolchain)
    if match_current_macos_toolchain and toolchain != collect_macos_toolchain():
        raise RuntimeError("provenance macOS toolchain differs from the current build host")

    artifact = require_object(manifest.get("artifact"), "provenance artifact")
    if not isinstance(artifact.get("file"), str) or not artifact["file"].endswith(".zip"):
        raise RuntimeError("provenance artifact filename is invalid")
    if not isinstance(artifact.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", artifact["sha256"]):
        raise RuntimeError("provenance artifact SHA-256 is invalid")
    if artifact_path is not None:
        artifact_path = artifact_path.resolve()
        if not artifact_path.is_file():
            raise RuntimeError("artifact referenced by provenance verification is missing")
        if artifact["file"] != artifact_path.name:
            raise RuntimeError("provenance artifact filename differs from retained artifact")
        if artifact["sha256"] != sha256_file(artifact_path):
            raise RuntimeError("provenance artifact SHA-256 differs from retained artifact")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provenance", type=Path, required=True)
    parser.add_argument("--artifact", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--module-id", required=True)
    parser.add_argument("--expected-checkout", required=True)
    parser.add_argument("--expected-generated-copies", type=int)
    parser.add_argument("--expected-workflow", default="")
    parser.add_argument("--expected-event", default="")
    parser.add_argument("--expected-workflow-source", default="")
    parser.add_argument("--require-macos-toolchain", action="store_true")
    parser.add_argument("--match-current-macos-toolchain", action="store_true")
    args = parser.parse_args()
    try:
        verify_provenance(
            args.provenance,
            args.repo_root,
            expected_source_sha=args.expected_source_sha,
            module_id=args.module_id,
            artifact_path=args.artifact,
            expected_checkout=args.expected_checkout,
            expected_generated_copies=args.expected_generated_copies,
            expected_workflow=args.expected_workflow,
            expected_event=args.expected_event,
            expected_workflow_source=args.expected_workflow_source,
            require_macos_toolchain=args.require_macos_toolchain,
            match_current_macos_toolchain=args.match_current_macos_toolchain,
        )
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(error, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
