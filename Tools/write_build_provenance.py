#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import plistlib
import re
import tempfile
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


def verified_derived_inputs(repo_root, mapping, tracked):
    """Accept only declared byte-for-byte copies of committed fixture inputs."""
    if not isinstance(mapping, dict):
        raise RuntimeError('derived input mapping must be an object')
    allowed, evidence = set(), []
    for destination, source in sorted(mapping.items()):
        if not isinstance(source, str) or not isinstance(destination, str):
            raise RuntimeError('derived input paths must be strings')
        paths = [Path(source), Path(destination)]
        if any(path.is_absolute() or '..' in path.parts or not path.parts or '.git' in path.parts
               for path in paths):
            raise RuntimeError('derived inputs must stay inside the checkout')
        source_path, destination_path = (repo_root / path for path in paths)
        if any(path.is_symlink() or not path.is_dir() or repo_root not in path.resolve().parents
               for path in (source_path, destination_path)):
            raise RuntimeError('derived inputs must be real directories inside the checkout')

        def files(directory):
            result = {}
            for path in directory.rglob('*'):
                if '__pycache__' in path.relative_to(directory).parts:
                    continue
                if path.is_symlink():
                    raise RuntimeError('derived input copies must not contain symlinks')
                if path.is_file():
                    result[path.relative_to(directory).as_posix()] = path
            return result

        originals, copies = files(source_path), files(destination_path)
        if not originals or set(originals) != set(copies):
            raise RuntimeError(f'derived input inventory does not match its source: {destination}')
        records = []
        for relative, original in sorted(originals.items()):
            copy = copies[relative]
            source_name = original.relative_to(repo_root).as_posix()
            target_name = copy.relative_to(repo_root).as_posix()
            if source_name not in tracked or target_name in tracked:
                raise RuntimeError('derived inputs must copy committed sources to untracked destinations')
            if (original.read_bytes() != copy.read_bytes()
                    or bool(original.stat().st_mode & 0o111) != bool(copy.stat().st_mode & 0o111)):
                raise RuntimeError(f'derived input differs from its source: {target_name}')
            allowed.add(target_name)
            records.append([relative, sha256_file(copy), bool(copy.stat().st_mode & 0o111)])
        evidence.append({'source': source, 'destination': destination,
                         'sha256': hashlib.sha256(json.dumps(records, separators=(',', ':')).encode()).hexdigest()})
    return allowed, evidence


def source_snapshot(repo_root: Path, *, derived_inputs=None, game_id=None) -> dict[str, object]:
    """Capture actual checkout bytes, including dirty/untracked source inputs."""
    repo_root = repo_root.resolve()
    try:
        top = Path(subprocess.check_output(
            ['git', 'rev-parse', '--show-toplevel'], cwd=repo_root,
            text=True, stderr=subprocess.DEVNULL).strip()).resolve()
        if top != repo_root:
            raise RuntimeError('source root must be the checkout root')
        source_sha = git_value(repo_root, 'HEAD')
        source_tree = git_value(repo_root, 'HEAD^{tree}')
    except subprocess.CalledProcessError:
        # Downloaded source trees may still be built, but never receive an
        # exact-commit artifact claim.
        source_sha = source_tree = None
        tracked = {}
        extras = {path.relative_to(repo_root).as_posix() for path in repo_root.rglob('*')
                  if path.is_file() and not set(path.relative_to(repo_root).parts)
                  & {'.git', 'dist', 'artifacts', '.build', '__pycache__', 'DerivedData'}}
    else:
        listing = subprocess.check_output(
            ['git', 'ls-tree', '-rz', '--full-tree', 'HEAD'], cwd=repo_root)
        tracked = {}
        for row in listing.split(b'\0'):
            if not row:
                continue
            metadata, name = row.split(b'\t', 1)
            mode, kind, blob = metadata.decode().split()
            if kind != 'blob':
                raise RuntimeError('Exact-source builds do not support unmaterialized Git submodules')
            tracked[name.decode()] = (mode, blob)
        extras = set(filter(None, subprocess.check_output(
            ['git', 'ls-files', '--others', '--exclude-standard', '-z'],
            cwd=repo_root).decode().split('\0')))
        # Git ignore rules do not stop compilers or backend packaging from
        # consuming a file. Include ignored inputs, except bytecode caches
        # that build.sh explicitly removes from the packaged backend.
        input_roots = ['Sources', 'Backend', 'Native', 'Tools', 'Resources',
                       'Info.plist', 'build.sh', 'ACTIVE_GAME_ID', 'AppIcon.icns']
        if game_id is not None:
            from module_support import load_manifest
            input_roots.extend(resource.source for resource in load_manifest(game_id, root=repo_root).app_resources)
        ignored = subprocess.check_output(
            ['git', 'ls-files', '--others', '--ignored', '--exclude-standard', '-z', '--', *input_roots],
            cwd=repo_root).decode().split('\0')
        extras.update(name for name in ignored if name and '__pycache__' not in Path(name).parts)
    derived_paths, derived_evidence = verified_derived_inputs(repo_root, derived_inputs or {}, tracked)
    dirty, records = [], []
    for name in sorted(set(tracked) | extras):
        path = repo_root / name
        if path.is_symlink():
            content = os.readlink(path).encode()
            mode = '120000'
        elif path.is_file():
            content = path.read_bytes()
            mode = '100755' if path.stat().st_mode & 0o111 else '100644'
        else:
            content, mode = b'', 'missing'
        blob = hashlib.sha1(b'blob ' + str(len(content)).encode() + b'\0' + content).hexdigest()
        records.append([name, mode, blob])
        if (mode == '120000' or tracked.get(name) != (mode, blob)) and name not in derived_paths:
            dirty.append(name)
    digest = hashlib.sha256(json.dumps(records, separators=(',', ':')).encode()).hexdigest()
    return {'commit': source_sha, 'tree': source_tree, 'inputsSha256': digest, 'dirtyPaths': dirty, 'derivedInputs': derived_evidence}


def require_exact_source(snapshot):
    if not snapshot['commit'] or snapshot['dirtyPaths']:
        raise RuntimeError('Exact-source provenance refuses unversioned, dirty or untracked build inputs: '
                           + ', '.join(snapshot['dirtyPaths'][:20]))


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
    *, derived_inputs=None, build_origin=None,
) -> dict[str, object]:
    snapshot = source_snapshot(repo_root, derived_inputs=derived_inputs,
                               game_id=build_origin['module']['id'] if build_origin else None)
    require_exact_source(snapshot)
    source_sha = snapshot['commit']
    source_tree = snapshot['tree']
    digest = sha256_file(artifact)
    ci_keys = ('GITHUB_ACTIONS', 'GITHUB_EVENT_NAME', 'GITHUB_WORKFLOW',
               'GITHUB_REPOSITORY', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT', 'GITHUB_RUN_NUMBER')
    is_ci = any(env.get(key, '').strip() for key in ci_keys)
    event_name = require_env(env, 'GITHUB_EVENT_NAME') if is_ci else None

    manifest: dict[str, object] = {
        "schemaVersion": 1,
        "buildInputs": {"sha256": snapshot["inputsSha256"], "derived": snapshot["derivedInputs"]},
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
        } if is_ci else None,
        "artifact": {
            "file": artifact.name,
            "sha256": digest,
        },
    }

    if build_origin is not None:
        if (build_origin['source'] != snapshot
                or build_origin['productVersion'] != product_version
                or build_origin['bundleBuild'] != bundle_build):
            raise RuntimeError('Artifact source changed since the app was built')
        manifest['module'] = build_origin['module']
        manifest['residentRuntime'] = build_origin['residentRuntime']

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
    *, derived_inputs=None, build_origin=None,
) -> tuple[Path, Path, dict[str, object]]:
    manifest = build_manifest(artifact, product_version, bundle_build, repo_root, env,
                              derived_inputs=derived_inputs, build_origin=build_origin)
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


BUILD_ORIGIN_FILE = 'BuildProvenance.json'


def release_identity(repo_root):
    from module_support import app_template
    info = app_template(repo_root)
    version, build = info.get('CFBundleShortVersionString'), info.get('CFBundleVersion')
    if not isinstance(version, str) or not re.fullmatch(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)', version):
        raise RuntimeError('Root Info.plist must declare a three-part product version')
    if not isinstance(build, str) or not re.fullmatch(r'[1-9][0-9]*', build):
        raise RuntimeError('Root Info.plist must declare a positive bundle build number')
    return version, build


def module_identity(manifest):
    from module_support import normalized_manifest
    return {'id': manifest.id, **normalized_manifest(manifest)['app']}


def resident_identity(manifest, app, repo_root):
    from resident_runtime import DECLARATION_KEY, parse_resident_runtime_declaration
    declaration = manifest.raw.get(DECLARATION_KEY)
    if declaration is None:
        return None
    module_path = repo_root / 'Backend/games' / manifest.id / 'module.json'
    spec = parse_resident_runtime_declaration(
        declaration, manifest_path=module_path,
        source_exists=lambda path: path.is_file() and not path.is_symlink())
    packaged_relative = Path('Contents/Resources/Backend/games') / manifest.id / spec.source
    packaged = app / packaged_relative
    if packaged.is_symlink() or not packaged.is_file() or app.resolve() not in packaged.resolve().parents:
        raise RuntimeError('Packaged resident source is missing or unsafe')
    source_digest, package_digest = sha256_file(spec.runtime_path), sha256_file(packaged)
    if source_digest != package_digest:
        raise RuntimeError('Packaged resident bytes differ from their declared source')
    return {'source': spec.runtime_path.relative_to(repo_root).as_posix(),
            'packagedPath': packaged_relative.as_posix(),
            'sourceSha256': source_digest, 'packagedSha256': package_digest}


def derived_mapping(snapshot):
    return {row['destination']: row['source'] for row in snapshot.get('derivedInputs', [])}


def seal_build(game_id, app, before, repo_root):
    """Bind a build to the source observed before compilation, before signing."""
    from module_support import load_manifest
    from verify_module_build import verify_module_build
    app, repo_root = Path(app).resolve(), Path(repo_root).resolve()
    after = source_snapshot(repo_root, derived_inputs=derived_mapping(before), game_id=game_id)
    if before != after:
        raise RuntimeError('Build inputs changed during compilation; rebuild before publishing')
    manifest = load_manifest(game_id, root=repo_root)
    verified = verify_module_build(game_id, app.parent, repo_root=repo_root)
    if verified != app:
        raise RuntimeError('Build app does not match the selected module')
    version, build = release_identity(repo_root)
    info = plistlib.loads((app / 'Contents/Info.plist').read_bytes())
    if info.get('CFBundleShortVersionString') != version or info.get('CFBundleVersion') != build:
        raise RuntimeError('Packaged product version differs from root Info.plist')
    origin = {'schemaVersion': 1, 'source': after, 'module': module_identity(manifest),
              'productVersion': version, 'bundleBuild': build,
              'residentRuntime': resident_identity(manifest, app, repo_root)}
    path = app / 'Contents/Resources' / BUILD_ORIGIN_FILE
    if path.is_symlink():
        raise RuntimeError('Build provenance must not be a symlink')
    path.write_text(json.dumps(origin, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return origin


def package_module(game_id, output_dir, repo_root, env):
    """One owner for artifact names, source binding, archive and sidecars."""
    from module_support import load_manifest
    from verify_module_build import verify_module_build
    repo_root, output_dir = Path(repo_root).resolve(), Path(output_dir).resolve()
    manifest = load_manifest(game_id, root=repo_root)
    app = verify_module_build(game_id, repo_root / 'dist', repo_root=repo_root)
    origin_path = app / 'Contents/Resources' / BUILD_ORIGIN_FILE
    if origin_path.is_symlink() or not origin_path.is_file():
        raise RuntimeError('App has no sealed build provenance; rebuild before packaging')
    origin = json.loads(origin_path.read_text(encoding='utf-8'))
    source = source_snapshot(repo_root, derived_inputs=derived_mapping(origin['source']), game_id=game_id)
    require_exact_source(source)
    if source != origin['source']:
        raise RuntimeError('Built app source differs from the checkout; rebuild before packaging')
    version, build = release_identity(repo_root)
    if (origin.get('schemaVersion') != 1 or origin.get('module') != module_identity(manifest)
            or origin.get('productVersion') != version or origin.get('bundleBuild') != build
            or origin.get('residentRuntime') != resident_identity(manifest, app, repo_root)):
        raise RuntimeError('Built app provenance does not match selected source/package identity')
    subprocess.run(['codesign', '--verify', '--deep', '--strict', str(app)],
                   check=True, cwd=repo_root, env=env)
    prefix = re.sub(r'[^A-Za-z0-9._-]+', '-', manifest.app.executable).strip('.-') or 'app'
    name = f"{prefix}-{manifest.id}-{version}-b{build}-{source['commit'][:8]}-rc.zip"
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.mgt-package-', dir=output_dir) as temporary:
        artifact = Path(temporary) / name
        subprocess.run(['ditto', '-c', '-k', '--sequesterRsrc', '--keepParent', str(app), str(artifact)],
                       check=True, cwd=repo_root, env=env)
        provenance, sidecar, metadata = write_metadata(
            artifact, version, build, repo_root, env,
            derived_inputs=derived_mapping(source), build_origin=origin)
        for path in (artifact, provenance, sidecar):
            os.replace(path, output_dir / path.name)
    return {'artifact': str(output_dir / name),
            'provenance': str(output_dir / provenance.name),
            'sidecar': str(output_dir / sidecar.name),
            'artifact_name': Path(name).stem,
            'source_sha': metadata['source']['commit'], 'source_tree': metadata['source']['tree']}


def main() -> int:
    parser = argparse.ArgumentParser(description='Record and package exact-source selected-module builds.')
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--capture-source', type=Path)
    mode.add_argument('--seal-app', type=Path)
    mode.add_argument('--package', metavar='GAME_ID')
    parser.add_argument('--game-id')
    parser.add_argument('--source-snapshot', type=Path)
    parser.add_argument('--repo-root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output-dir', type=Path, default=Path('artifacts'))
    parser.add_argument('--github-output', type=Path)
    args = parser.parse_args()
    root = args.repo_root.resolve()
    try:
        if args.capture_source:
            if not args.game_id:
                parser.error('--capture-source requires --game-id')
            mapping = json.loads(os.environ.get('MGT_BUILD_DERIVED_INPUTS', '{}'))
            snapshot = source_snapshot(root, derived_inputs=mapping, game_id=args.game_id)
            args.capture_source.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + '\n')
        elif args.seal_app:
            if not args.game_id or not args.source_snapshot:
                parser.error('--seal-app requires --game-id and --source-snapshot')
            before = json.loads(args.source_snapshot.read_text(encoding='utf-8'))
            seal_build(args.game_id, args.seal_app, before, root)
        else:
            result = package_module(args.package, args.output_dir, root, os.environ)
            if args.github_output:
                if any('\n' in value or '\r' in value for value in result.values()):
                    raise RuntimeError('Artifact output fields must be single-line values')
                with args.github_output.open('a', encoding='utf-8') as stream:
                    for key, value in result.items():
                        stream.write(f'{key}={value}\n')
            print(json.dumps(result, indent=2, sort_keys=True))
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.CalledProcessError) as error:
        parser.exit(2, f'Build provenance failed: {error}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
