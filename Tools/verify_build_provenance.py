#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path

from macos_toolchain_identity import (
    collect_macos_toolchain,
    verify_recorded_macos_toolchain,
)
from write_build_provenance import (
    git_value,
    packaged_content_claims,
    product_module_ids,
    require_product_identity,
    sha256_file,
)


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
    artifact_path: Path,
    expected_checkout: str,
    expected_generated_copies: int | None = None,
    expected_workflow: str = "",
    expected_event: str = "",
    expected_workflow_source: str = "",
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
    source_plist = require_product_identity(repo_root, product_version, bundle_build)

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

    selected = ids if module_id == 'all' else (module_id,)
    expected_supported = {
        game_id: identity for game_id in selected
        if (identity := json.loads((repo_root / 'Backend/games' / game_id / 'module.json').read_text(encoding='utf-8')).get('supportedBuild')) is not None
    }
    if manifest.get('supportedBuilds') != expected_supported:
        raise RuntimeError('provenance supported game build identities differ from module declarations')

    # Every producer packages on a macOS runner and records its toolchain.
    toolchain = manifest.get("toolchain")
    verify_recorded_macos_toolchain(toolchain)
    if match_current_macos_toolchain and toolchain != collect_macos_toolchain():
        raise RuntimeError("provenance macOS toolchain differs from the current build host")

    artifact = require_object(manifest.get("artifact"), "provenance artifact")
    if not isinstance(artifact.get("file"), str) or not artifact["file"].endswith(".zip"):
        raise RuntimeError("provenance artifact filename is invalid")
    artifact_path = artifact_path.resolve()
    if not artifact_path.is_file():
        raise RuntimeError("artifact referenced by provenance verification is missing")
    if artifact["file"] != artifact_path.name:
        raise RuntimeError("provenance artifact filename differs from retained artifact")
    if artifact.get("sha256") != sha256_file(artifact_path):
        raise RuntimeError("provenance artifact SHA-256 differs from retained artifact")

    # A matching digest identifies the retained ZIP, not its contents: the
    # app bundle identity and every packaged claim come from the ZIP itself.
    claims = packaged_content_claims(repo_root, artifact_path, module_id, source_plist)
    for field, name in (("pythonRuntime", "Python runtime"),
                        ("residentRuntime", "resident runtime"),
                        ("residentRuntimes", "resident runtimes")):
        if manifest.get(field) != claims.get(field):
            raise RuntimeError(f"provenance {name} differs from source declarations and retained artifact")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provenance", type=Path, required=True)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--module-id", required=True)
    parser.add_argument("--expected-checkout", required=True)
    parser.add_argument("--expected-generated-copies", type=int)
    parser.add_argument("--expected-workflow", default="")
    parser.add_argument("--expected-event", default="")
    parser.add_argument("--expected-workflow-source", default="")
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
            match_current_macos_toolchain=args.match_current_macos_toolchain,
        )
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError, zipfile.BadZipFile) as error:
        print(error, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
