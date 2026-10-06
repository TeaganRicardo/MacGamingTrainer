#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import plistlib
import re
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Mapping

from resident_runtime import parse_resident_runtime_declaration
from module_support import app_spec_from_manifest


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


def require_product_identity(repo_root: Path, product_version: str,
                             bundle_build: str) -> dict[str, object]:
    """Check caller values against the sole product-version source."""
    if not re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", product_version):
        raise RuntimeError("product version must be three-part SemVer")
    if not re.fullmatch(r"[1-9][0-9]*", bundle_build):
        raise RuntimeError("bundle build must be a positive integer")
    plist = plistlib.loads((repo_root / "Info.plist").read_bytes())
    if plist.get("CFBundleShortVersionString") != product_version:
        raise RuntimeError("product version differs from Info.plist CFBundleShortVersionString")
    if plist.get("CFBundleVersion") != bundle_build:
        raise RuntimeError("bundle build differs from Info.plist CFBundleVersion")
    executable = plist.get("CFBundleExecutable")
    if (not isinstance(executable, str) or not executable or executable in (".", "..")
            or any(character in executable for character in ("/", ":", "\\"))
            or any(ord(character) < 32 for character in executable)):
        raise RuntimeError("Info.plist CFBundleExecutable is not a safe artifact stem")
    return plist


def artifact_name(repo_root: Path, product_version: str, bundle_build: str,
                  label: str = "") -> str:
    """One owner for artifact names; product identity comes from Info.plist."""
    plist = require_product_identity(repo_root, product_version, bundle_build)
    return _artifact_name(plist, product_version, bundle_build, git_value(repo_root, "HEAD"), label)


def _artifact_name(plist: dict[str, object], product_version: str, bundle_build: str,
                   source_sha: str, label: str) -> str:
    if label and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", label):
        raise RuntimeError("artifact label must be a safe identifier")
    executable = plist["CFBundleExecutable"]
    stem = executable + (f"-{label}" if label else "")
    return f"{stem}-{product_version}-b{bundle_build}-{source_sha[:8]}-rc.zip"


def _copy_files(path: Path) -> dict[str, str]:
    if not path.is_dir() or path.is_symlink():
        raise RuntimeError(f"generated copy directory is missing or unsafe: {path}")
    files = {}
    for entry in path.rglob("*"):
        relative = entry.relative_to(path)
        if "__pycache__" in relative.parts or entry.suffix == ".pyc":
            continue  # build.sh removes Python caches from the package
        if entry.is_symlink():
            raise RuntimeError(f"generated copy contains a symlink: {entry}")
        if entry.is_file():
            files[relative.as_posix()] = sha256_file(entry)
    return files


def require_declared_inputs(repo_root: Path, copy_specs: tuple[str, ...]) -> list[dict[str, str]]:
    """Reject undisclosed worktree inputs, including generated module copies."""
    declared = []
    allowed = set()
    for spec in copy_specs:
        if ":" not in spec:
            raise RuntimeError("--generated-copy requires SOURCE:DESTINATION")
        source_name, dest_name = spec.split(":", 1)
        paths = [Path(name) for name in (source_name, dest_name)]
        if any(path.is_absolute() or not path.parts or ".." in path.parts for path in paths):
            raise RuntimeError(f"generated copy path must stay inside the repository: {spec}")
        source, destination = [(repo_root / path).resolve() for path in paths]
        if any(repo_root not in path.parents for path in (source, destination)):
            raise RuntimeError(f"generated copy path escapes the repository: {spec}")
        files = _copy_files(source)
        if not files or files != _copy_files(destination):
            raise RuntimeError(f"generated copy differs from declared source: {dest_name}")
        for relative in files:
            source_file = (paths[0] / relative).as_posix()
            subprocess.run(["git", "ls-files", "--error-unmatch", "--", source_file],
                           cwd=repo_root, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, check=True)
            allowed.add((paths[1] / relative).as_posix())
        digest = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
        declared.append({"source": source_name, "destination": dest_name, "sha256": digest})

    status = subprocess.check_output(
        ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"], cwd=repo_root
    ).decode("utf-8", errors="replace")
    unexpected = []
    for entry in status.split("\x00"):
        if not entry:
            continue
        code, path = entry[:2], entry[3:]
        if code == "??" and path in allowed:
            continue
        unexpected.append(path)
    if unexpected:
        raise RuntimeError("source checkout has dirty or untracked inputs: " + ", ".join(unexpected[:8]))

    ignored = subprocess.check_output(
        ["git", "ls-files", "--others", "--ignored", "--exclude-standard", "-z", "--",
         "Backend", "Sources", "Resources", "Native", "Tools", "ContractFixtures"], cwd=repo_root
    ).decode("utf-8", errors="replace")
    for path in ignored.split("\x00"):
        if not path or "__pycache__" in Path(path).parts or path.endswith(".pyc"):
            continue
        raise RuntimeError(f"source checkout has ignored build input: {path}")
    return declared


def resident_identity(repo_root: Path, artifact: Path, module_id: str,
                      app_root: str) -> dict[str, str] | None:
    """Hash the resident file named by the selected module, in source and ZIP."""
    manifest_path = repo_root / "Backend/games" / module_id / "module.json"
    declaration = json.loads(manifest_path.read_text(encoding="utf-8")).get("residentRuntime")
    if declaration is None:
        return None
    spec = parse_resident_runtime_declaration(
        declaration, manifest_path=manifest_path,
        source_exists=lambda path: path.is_file() and not path.is_symlink(),
    )
    packaged_path = f"{app_root}/Contents/Resources/Backend/games/{module_id}/{spec.source}"
    with zipfile.ZipFile(artifact) as archive:
        if archive.namelist().count(packaged_path) != 1:
            raise RuntimeError(f"selected app must contain exactly one declared resident source: {packaged_path}")
        packaged_digest = hashlib.sha256(archive.read(packaged_path)).hexdigest()
    source_digest = sha256_file(spec.runtime_path)
    if source_digest != packaged_digest:
        raise RuntimeError("packaged resident source differs from declared source")
    return {
        "source": spec.runtime_path.relative_to(repo_root).as_posix(),
        "sourceSha256": source_digest,
        "packagedPath": packaged_path,
        "packagedSha256": packaged_digest,
    }


def python_runtime_identity(repo_root: Path, artifact: Path,
                            app_root: str) -> dict[str, object] | None:
    """Bind bundled Python provenance to the tracked declaration and ZIP metadata."""
    source_path = repo_root / "Tools/python_runtime.json"
    if not source_path.is_file() or source_path.is_symlink():
        return None

    source_bytes = source_path.read_bytes()
    source = json.loads(source_bytes)
    if not isinstance(source, dict):
        raise RuntimeError("Python runtime source manifest must be an object")

    packaged_path = f"{app_root}/Contents/Resources/Python/runtime.json"
    with zipfile.ZipFile(artifact) as archive:
        if archive.namelist().count(packaged_path) != 1:
            raise RuntimeError(
                f"selected app must contain exactly one Python runtime manifest: {packaged_path}"
            )
        packaged_bytes = archive.read(packaged_path)
    packaged = json.loads(packaged_bytes)
    if not isinstance(packaged, dict):
        raise RuntimeError("packaged Python runtime manifest must be an object")

    for field in ("schemaVersion", "provider", "release", "version"):
        if packaged.get(field) != source.get(field):
            raise RuntimeError(
                f"packaged Python runtime {field} differs from tracked declaration"
            )

    architectures = packaged.get("architectures")
    if (
        not isinstance(architectures, list)
        or not architectures
        or any(not isinstance(arch, str) or not arch for arch in architectures)
        or len(set(architectures)) != len(architectures)
    ):
        raise RuntimeError("packaged Python runtime architectures are invalid")

    source_distributions = source.get("distributions")
    packaged_distributions = packaged.get("distributions")
    if not isinstance(source_distributions, dict) or not isinstance(packaged_distributions, dict):
        raise RuntimeError("Python runtime distributions must be objects")
    try:
        selected_distributions = {
            arch: source_distributions[arch]
            for arch in architectures
        }
    except KeyError as error:
        raise RuntimeError(
            f"packaged Python runtime architecture is not declared: {error.args[0]}"
        ) from error
    if packaged_distributions != selected_distributions:
        raise RuntimeError(
            "packaged Python runtime distributions differ from tracked declaration"
        )

    return {
        "manifest": "Tools/python_runtime.json",
        "sourceSha256": hashlib.sha256(source_bytes).hexdigest(),
        "packagedPath": packaged_path,
        "packagedMetadataSha256": hashlib.sha256(packaged_bytes).hexdigest(),
        "schemaVersion": source.get("schemaVersion"),
        "provider": source.get("provider"),
        "release": source.get("release"),
        "version": source.get("version"),
        "architectures": architectures,
        "distributions": selected_distributions,
    }


def require_packaged_module_identity(repo_root: Path, artifact: Path, module_id: str,
                                     source_plist: dict[str, object]) -> str:
    """Bind the claimed module and product identity to the packaged app."""
    if not re.fullmatch(r"[a-z][a-z0-9_]*", module_id):
        raise RuntimeError(f"invalid module id: {module_id!r}")
    source_manifest = (repo_root / "Backend/games" / module_id / "module.json").read_bytes()
    source_data = json.loads(source_manifest)
    if not isinstance(source_data, dict) or source_data.get("id") != module_id:
        raise RuntimeError("source module manifest ID differs from --module-id")
    game_display_name = source_data.get("displayName")
    if not isinstance(game_display_name, str) or not game_display_name.strip():
        raise RuntimeError("source module manifest has no displayName")
    app = app_spec_from_manifest(
        source_data, module_id, game_display_name.strip(), source_plist["CFBundleExecutable"]
    )
    marker_suffix = "/Contents/Resources/ACTIVE_GAME_ID"
    with zipfile.ZipFile(artifact) as archive:
        names = archive.namelist()
        markers = [name for name in names if name.endswith(marker_suffix)]
        if len(markers) != 1:
            raise RuntimeError("artifact must contain exactly one selected-module marker")
        app_root = markers[0][:-len(marker_suffix)]
        if app_root != f"{app.display_name}.app":
            raise RuntimeError("artifact app name differs from declared module identity")
        if archive.read(markers[0]).decode("utf-8").strip() != module_id:
            raise RuntimeError("packaged module marker differs from --module-id")
        info_path = f"{app_root}/Contents/Info.plist"
        if names.count(info_path) != 1:
            raise RuntimeError("artifact must contain exactly one packaged Info.plist")
        packaged_info = plistlib.loads(archive.read(info_path))
        expected_info = {
            "CFBundleShortVersionString": source_plist["CFBundleShortVersionString"],
            "CFBundleVersion": source_plist["CFBundleVersion"],
            "CFBundleExecutable": app.executable,
            "CFBundleIdentifier": app.bundle_identifier,
            "CFBundleName": app.display_name,
            "CFBundleDisplayName": app.display_name,
        }
        for field, expected in expected_info.items():
            if packaged_info.get(field) != expected:
                raise RuntimeError(f"packaged Info.plist {field} differs from declared source")
        module_dir = f"{app_root}/Contents/Resources/Backend/games/"
        packaged_manifest = f"{module_dir}{module_id}/module.json"
        manifests = [name for name in names if name.startswith(module_dir)
                     and name.endswith("/module.json")]
        if manifests != [packaged_manifest]:
            raise RuntimeError("artifact must contain exactly one selected module manifest")
        packaged_bytes = archive.read(packaged_manifest)
        if json.loads(packaged_bytes).get("id") != module_id:
            raise RuntimeError("packaged module manifest ID differs from --module-id")
        if packaged_bytes != source_manifest:
            raise RuntimeError("packaged module manifest differs from declared source")
    return app_root


def build_manifest(
    artifact: Path,
    product_version: str,
    bundle_build: str,
    repo_root: Path,
    env: Mapping[str, str],
    *,
    local: bool = False,
    generated_copies: tuple[str, ...] = (),
    module_id: str = "",
    name_label: str = "",
) -> dict[str, object]:
    source_plist = require_product_identity(repo_root, product_version, bundle_build)
    source_sha = git_value(repo_root, "HEAD")
    source_tree = git_value(repo_root, "HEAD^{tree}")
    expected_name = _artifact_name(source_plist, product_version, bundle_build, source_sha, name_label)
    if artifact.name != expected_name:
        raise RuntimeError(f"artifact name differs from declared source: expected {expected_name}")
    copies = require_declared_inputs(repo_root, generated_copies)
    digest = sha256_file(artifact)
    if local and (env.get("GITHUB_ACTIONS") == "true" or env.get("GITHUB_EVENT_NAME")):
        raise RuntimeError("--local cannot be used in a GitHub workflow")

    manifest: dict[str, object] = {
        "schemaVersion": 1,
        "productVersion": product_version,
        "bundleBuild": bundle_build,
        "source": {"commit": source_sha, "tree": source_tree},
        "buildInputs": {"checkout": "declared-generated" if copies else "clean",
                        "generatedCopies": copies},
        "artifact": {"file": artifact.name, "sha256": digest},
        "origin": "local" if local else "github",
    }

    if not local:
        event_name = require_env(env, "GITHUB_EVENT_NAME")
        manifest["workflow"] = {
            "eventName": event_name,
            "name": require_env(env, "GITHUB_WORKFLOW"),
            "repository": require_env(env, "GITHUB_REPOSITORY"),
            "runId": require_env(env, "GITHUB_RUN_ID"),
            "runAttempt": require_env(env, "GITHUB_RUN_ATTEMPT"),
            "runNumber": require_env(env, "GITHUB_RUN_NUMBER"),
        }
        if event_name == "pull_request":
            event_path = Path(require_env(env, "GITHUB_EVENT_PATH"))
            payload = json.loads(event_path.read_text(encoding="utf-8"))
            pull_request = payload.get("pull_request")
            if not isinstance(pull_request, dict):
                raise RuntimeError("pull_request event is missing pull_request metadata")
            head, base = pull_request.get("head"), pull_request.get("base")
            if not isinstance(head, dict) or not isinstance(base, dict):
                raise RuntimeError("pull_request event is missing head/base metadata")
            head_sha, base_sha = head.get("sha"), base.get("sha")
            if not isinstance(head_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", head_sha):
                raise RuntimeError("pull_request event has invalid head SHA")
            if not isinstance(base_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", base_sha):
                raise RuntimeError("pull_request event has invalid base SHA")
            if head_sha != source_sha:
                raise RuntimeError(f"pull_request head {head_sha} differs from executing checkout {source_sha}")
            manifest["pullRequest"] = {
                "number": payload.get("number"), "headSha": head_sha, "baseSha": base_sha,
            }
        elif event_name == "push" and require_env(env, "GITHUB_SHA") != source_sha:
            raise RuntimeError("push event SHA differs from executing checkout")

    if module_id:
        app_root = require_packaged_module_identity(repo_root, artifact, module_id, source_plist)
        manifest["moduleId"] = module_id
        python_runtime = python_runtime_identity(repo_root, artifact, app_root)
        if python_runtime is not None:
            manifest["pythonRuntime"] = python_runtime
        resident = resident_identity(repo_root, artifact, module_id, app_root)
        if resident is not None:
            manifest["residentRuntime"] = resident

    return manifest


def write_metadata(
    artifact: Path,
    product_version: str,
    bundle_build: str,
    repo_root: Path,
    env: Mapping[str, str],
    *,
    local: bool = False,
    generated_copies: tuple[str, ...] = (),
    module_id: str = "",
    name_label: str = "",
) -> tuple[Path, Path, dict[str, object]]:
    manifest = build_manifest(
        artifact, product_version, bundle_build, repo_root, env,
        local=local, generated_copies=generated_copies, module_id=module_id,
        name_label=name_label,
    )
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
    parser.add_argument("--artifact", type=Path)
    parser.add_argument("--print-artifact-name", action="store_true")
    parser.add_argument("--product-version", required=True)
    parser.add_argument("--bundle-build", required=True)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--name-label", default="")
    parser.add_argument("--module-id", default="")
    parser.add_argument("--generated-copy", action="append", default=[])
    parser.add_argument("--local", action="store_true")
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    try:
        if args.print_artifact_name:
            if args.artifact:
                raise RuntimeError("--artifact is not used with --print-artifact-name")
            print(artifact_name(repo_root, args.product_version, args.bundle_build, args.name_label))
            return 0
        if args.artifact is None:
            raise RuntimeError("--artifact is required to write provenance")
        artifact = args.artifact.resolve()
        if not artifact.is_file():
            raise RuntimeError(f"artifact does not exist: {artifact}")
        provenance, sidecar, manifest = write_metadata(
            artifact, args.product_version, args.bundle_build, repo_root, os.environ,
            local=args.local, generated_copies=tuple(args.generated_copy),
            module_id=args.module_id, name_label=args.name_label,
        )
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError, zipfile.BadZipFile) as error:
        print(f"Unable to write build provenance: {error}", file=sys.stderr)
        return 2
    source = manifest["source"]
    if not isinstance(source, dict):
        raise RuntimeError("invalid source metadata")
    print(f"source_sha={source['commit']}")
    print(f"source_tree={source['tree']}")
    print(f"provenance={provenance}")
    print(f"sidecar={sidecar}")
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with Path(github_output).open("a", encoding="utf-8") as handle:
            handle.write(f"artifact_name={artifact.name}\n")
            handle.write(f"provenance_name={provenance.name}\n")
            handle.write(f"sidecar_name={sidecar.name}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
