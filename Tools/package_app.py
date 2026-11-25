#!/usr/bin/env python3
"""Importable packaging helpers and shared Python runtime metadata schema owner."""
from __future__ import annotations

import argparse
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Sequence
from urllib.parse import urlparse

TOOLS_DIR = Path(__file__).resolve().parent
ROOT = TOOLS_DIR.parent
BACKEND = ROOT / "Backend"

SUPPORTED_RUNTIME_ARCHITECTURES = ("arm64", "x86_64")
HOST_LANGUAGES = ("en", "zh-CN")


def manifest_field(manifest_path: Path, field_path: str) -> str:
    """Resolve a dotted field from a normalized build selection manifest for shell callers."""
    value: object = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    for part in field_path.split("."):
        value = value.get(part) if isinstance(value, dict) else None
        if value is None:
            break
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, list):
        return " ".join(str(item) for item in value)
    if value is None:
        return ""
    return str(value)


def prepare_swift_inputs(manifest_path: Path, root: Path, generated_dir: Path, lists_dir: Path) -> list[str]:
    """Write per-module Swift source lists and return TSV lines of `(name, role, dependencies)`."""
    root = Path(root)
    tools_path = str(root / "Tools")
    if tools_path not in sys.path:
        sys.path.insert(0, tools_path)
    from product_support import swift_module_sources

    lists = Path(lists_dir)
    lists.mkdir(parents=True, exist_ok=True)
    layout = json.loads(Path(manifest_path).read_text(encoding="utf-8"))["frontend"]["swift"]["modules"]
    roles = [module["role"] for module in layout]
    if roles[-1:] != ["app"] or roles.count("app") != 1:
        raise ValueError("The Swift layout must end with exactly one App module.")
    modules = swift_module_sources(layout, root, Path(generated_dir))
    lines = []
    for module, sources in modules:
        name = module["name"]
        (lists / f"{name}.txt").write_text("".join(f"{source}\n" for source in sources), encoding="utf-8")
        lines.append("\t".join((name, module["role"], ",".join(module["dependencies"]))))
    return lines


def build_python_runtime_metadata(source: dict, architectures: Iterable[str]) -> dict:
    """Construct the canonical packaged `Python/runtime.json` payload for `architectures`."""
    if not isinstance(source, dict):
        raise ValueError("Python runtime source manifest must be an object")
    if type(source.get('schemaVersion')) is not int or source['schemaVersion'] != 1:
        raise ValueError('Python runtime schemaVersion must be 1')
    for field in ('provider', 'release', 'version'):
        if not isinstance(source.get(field), str) or not source[field].strip():
            raise ValueError(f'Python runtime {field} must be a non-empty string')
    arch_list = list(architectures)
    if (
        not arch_list
        or any(not isinstance(arch, str) or not arch for arch in arch_list)
        or len(set(arch_list)) != len(arch_list)
    ):
        raise ValueError("packaged Python runtime architectures are invalid")
    distributions = source.get("distributions")
    if not isinstance(distributions, dict):
        raise ValueError("Python runtime distributions must be objects")
    selected = {}
    for arch in arch_list:
        declaration = distributions.get(arch)
        if not isinstance(declaration, dict):
            raise ValueError(f"packaged Python runtime architecture is not declared: {arch}")
        if not isinstance(declaration.get('target'), str) or not declaration['target'].strip():
            raise ValueError(f'Python runtime target is missing for {arch}')
        url = declaration.get('url')
        if not isinstance(url, str) or urlparse(url).scheme != 'https' or not urlparse(url).netloc:
            raise ValueError(f'Python runtime URL is invalid for {arch}')
        digest = declaration.get('sha256')
        if not isinstance(digest, str) or not re.fullmatch(r'[0-9a-fA-F]{64}', digest):
            raise ValueError(f'Python runtime SHA-256 is invalid for {arch}')
        selected[arch] = declaration
    if any(arch not in SUPPORTED_RUNTIME_ARCHITECTURES for arch in arch_list):
        raise ValueError(f"Python runtime has unsupported target architecture: {arch_list}")
    return {
        "schemaVersion": source.get("schemaVersion"),
        "provider": source.get("provider"),
        "release": source.get("release"),
        "version": source.get("version"),
        "architectures": arch_list,
        "distributions": selected,
    }


def verify_python_runtime_metadata(
    source: dict,
    packaged: dict,
    *,
    expected_architectures: Sequence[str] | None = None,
) -> dict:
    """Validate a packaged `Python/runtime.json` mapping against the tracked `python_runtime.json` declaration."""
    if not isinstance(source, dict):
        raise ValueError("Python runtime source manifest must be an object")
    if not isinstance(packaged, dict):
        raise ValueError("packaged Python runtime manifest must be an object")
    for field in ("schemaVersion", "provider", "release", "version"):
        if packaged.get(field) != source.get(field):
            raise ValueError(f"packaged Python runtime {field} differs from tracked declaration")
    architectures = packaged.get("architectures")
    if (
        not isinstance(architectures, list)
        or not architectures
        or any(not isinstance(arch, str) or not arch for arch in architectures)
        or len(set(architectures)) != len(architectures)
    ):
        raise ValueError("packaged Python runtime architectures are invalid")
    if expected_architectures is not None:
        expected_list = list(expected_architectures)
        if any(arch not in SUPPORTED_RUNTIME_ARCHITECTURES for arch in expected_list):
            raise ValueError(f"Python runtime has unsupported target architecture: {expected_list}")
    source_distributions = source.get("distributions")
    packaged_distributions = packaged.get("distributions")
    if not isinstance(source_distributions, dict) or not isinstance(packaged_distributions, dict):
        raise ValueError("Python runtime distributions must be objects")
    target_arches = list(expected_architectures) if expected_architectures is not None else architectures
    expected = build_python_runtime_metadata(source, target_arches)
    if packaged_distributions != expected["distributions"]:
        raise ValueError("packaged Python runtime distributions differ from tracked declaration")
    if packaged != expected:
        raise ValueError("Python runtime metadata differs from pinned build input")
    return expected


def write_python_runtime_metadata(source_path: Path, output_path: Path, architectures: Sequence[str]) -> dict:
    """Write `Python/runtime.json` for the selected architectures."""
    source = json.loads(Path(source_path).read_text(encoding="utf-8"))
    metadata = build_python_runtime_metadata(source, architectures)
    Path(output_path).write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return metadata


def verify_host_localization(
    source_root: Path,
    resources_dir: Path,
    *,
    languages: Sequence[str] = HOST_LANGUAGES,
) -> None:
    """Verify packaged Host.strings tables match their tracked source tables byte-for-byte."""
    source_root, resources_dir = Path(source_root), Path(resources_dir)
    for language in languages:
        source = source_root / f"{language}.lproj/Host.strings"
        packaged = resources_dir / f"{language}.lproj/Host.strings"
        if not packaged.is_file() or packaged.read_bytes() != source.read_bytes():
            raise ValueError(f"Host localization package mismatch: {packaged}")


def package_app_resources(manifest_path: Path, root: Path, resources_dir: Path) -> None:
    """Copy declared module `appResources` into `Contents/Resources/`."""
    root = Path(root).resolve()
    resources = Path(resources_dir).resolve()
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    for item in manifest.get("appResources", []):
        source = (root / item["source"]).resolve()
        destination = (resources / item["destination"]).resolve()
        if root not in source.parents or not source.is_file():
            raise ValueError(f"Invalid/missing app resource source: {item['source']}")
        if resources not in destination.parents:
            raise ValueError(f"App resource destination escapes Contents/Resources: {item['destination']}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        if not destination.is_file():
            raise ValueError(f"App resource was not packaged: {item['destination']}")


def smoke_packaged_adapters(backend_dir: Path, requires_lldb: bool, game_ids: Sequence[str]) -> None:
    """Import and instantiate each packaged adapter against the staged Backend directory."""
    result = subprocess.run([
        sys.executable, '-I', '-c',
        "import runpy, sys; from pathlib import Path; "
        "runpy.run_path(sys.argv[1])['_smoke_packaged_adapters'](Path(sys.argv[2]), sys.argv[3] == '1', sys.argv[4:])",
        str(Path(__file__).resolve()), str(Path(backend_dir).resolve()), '1' if requires_lldb else '0', *game_ids,
    ], capture_output=True, text=True)
    if result.returncode:
        raise ValueError(f'Packaged adapter smoke failed: {result.stderr.strip()}')


def _smoke_packaged_adapters(backend_dir: Path, requires_lldb: bool, game_ids: Sequence[str]) -> None:
    """Run inside the fresh interpreter owned by ``smoke_packaged_adapters``."""
    resolved_backend = Path(backend_dir).resolve()
    if str(resolved_backend) not in sys.path:
        sys.path.insert(0, str(resolved_backend))
    from core.registry import create_adapter

    if requires_lldb:
        import debugger.lldb_time_warp as time_warp

        expected = resolved_backend / "debugger/lldb_time_warp.py"
        if Path(time_warp.__file__).resolve() != expected.resolve():
            raise ValueError("Debugger driver was not imported from the packaged backend.")
    for game_id in game_ids:
        adapter = create_adapter(game_id)
        try:
            metadata = adapter.metadata()
            if metadata.get("id") != game_id:
                raise ValueError(f"Backend adapter identity mismatch: {metadata!r}")
        finally:
            adapter.close()


def write_game_modules_marker(manifest_path: Path, output_path: Path) -> None:
    """Write `Contents/Resources/GAME_MODULES.json` from the normalized selection manifest."""
    selection = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    Path(output_path).write_text(json.dumps(selection["moduleIDs"]) + "\n", encoding="utf-8")


def patch_info_plist(
    plist_path: Path,
    bundle_id: str,
    app_name: str,
    minimum_macos: str,
    has_icon: bool,
    asset_info_path: Path,
    architectures: Sequence[str],
) -> None:
    """Patch `Contents/Info.plist` with selected identity, deployment target, architectures, and accent color."""
    path = Path(plist_path)
    asset_info = plistlib.loads(Path(asset_info_path).read_bytes())
    with path.open("rb") as stream:
        data = plistlib.load(stream)
    data["CFBundleIdentifier"] = bundle_id
    data["CFBundleName"] = app_name
    data["CFBundleDisplayName"] = app_name
    data["LSMinimumSystemVersion"] = minimum_macos
    data["LSArchitecturePriority"] = list(architectures)
    if has_icon:
        data["CFBundleIconFile"] = "AppIcon"
    else:
        data.pop("CFBundleIconFile", None)
    data["NSAccentColorName"] = asset_info["NSAccentColorName"]
    with path.open("wb") as stream:
        plistlib.dump(data, stream, sort_keys=False)


def merge_entitlements(manifest_path: Path, root: Path, destination: Path) -> None:
    """Merge declared module entitlements into a single plist, rejecting conflicting values."""
    manifest = Path(manifest_path)
    root = Path(root)
    merged: dict[str, object] = {}
    for relative in json.loads(manifest.read_text(encoding="utf-8"))["buildRequirements"]["entitlements"]:
        values = plistlib.loads((root / relative).read_bytes())
        for key, value in values.items():
            if key in merged and merged[key] != value:
                raise ValueError(f"Incompatible module entitlement: {key}")
            merged[key] = value
    Path(destination).write_bytes(plistlib.dumps(merged))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_field = subparsers.add_parser("manifest-field")
    p_field.add_argument("manifest", type=Path)
    p_field.add_argument("field")

    p_swift = subparsers.add_parser("prepare-swift-inputs")
    p_swift.add_argument("manifest", type=Path)
    p_swift.add_argument("root", type=Path)
    p_swift.add_argument("generated", type=Path)
    p_swift.add_argument("lists", type=Path)

    p_runtime = subparsers.add_parser("write-runtime-metadata")
    p_runtime.add_argument("source", type=Path)
    p_runtime.add_argument("output", type=Path)
    p_runtime.add_argument("architectures", nargs="+")

    p_loc = subparsers.add_parser("verify-host-localization")
    p_loc.add_argument("source_root", type=Path)
    p_loc.add_argument("resources", type=Path)

    p_res = subparsers.add_parser("package-app-resources")
    p_res.add_argument("manifest", type=Path)
    p_res.add_argument("root", type=Path)
    p_res.add_argument("resources", type=Path)

    p_smoke = subparsers.add_parser("smoke-adapters")
    p_smoke.add_argument("requires_lldb")
    p_smoke.add_argument("game_ids", nargs="+")

    p_modules = subparsers.add_parser("write-game-modules")
    p_modules.add_argument("manifest", type=Path)
    p_modules.add_argument("output", type=Path)

    p_plist = subparsers.add_parser("patch-info-plist")
    p_plist.add_argument("plist", type=Path)
    p_plist.add_argument("bundle_id")
    p_plist.add_argument("app_name")
    p_plist.add_argument("minimum_macos")
    p_plist.add_argument("has_icon")
    p_plist.add_argument("asset_info", type=Path)
    p_plist.add_argument("architectures", nargs="+")

    p_ent = subparsers.add_parser("merge-entitlements")
    p_ent.add_argument("manifest", type=Path)
    p_ent.add_argument("root", type=Path)
    p_ent.add_argument("destination", type=Path)

    args = parser.parse_args(argv)
    try:
        if args.command == "manifest-field":
            print(manifest_field(args.manifest, args.field))
        elif args.command == "prepare-swift-inputs":
            for line in prepare_swift_inputs(args.manifest, args.root, args.generated, args.lists):
                print(line)
        elif args.command == "write-runtime-metadata":
            write_python_runtime_metadata(args.source, args.output, args.architectures)
        elif args.command == "verify-host-localization":
            verify_host_localization(args.source_root, args.resources)
        elif args.command == "package-app-resources":
            package_app_resources(args.manifest, args.root, args.resources)
        elif args.command == "smoke-adapters":
            backend_env = os.environ.get("PYTHONPATH")
            backend_dir = Path(backend_env) if backend_env else BACKEND
            smoke_packaged_adapters(backend_dir, args.requires_lldb == "1", args.game_ids)
        elif args.command == "write-game-modules":
            write_game_modules_marker(args.manifest, args.output)
        elif args.command == "patch-info-plist":
            patch_info_plist(
                args.plist,
                args.bundle_id,
                args.app_name,
                args.minimum_macos,
                args.has_icon == "1",
                args.asset_info,
                args.architectures,
            )
        elif args.command == "merge-entitlements":
            merge_entitlements(args.manifest, args.root, args.destination)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
