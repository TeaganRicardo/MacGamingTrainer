#!/usr/bin/env python3
"""Single supported-game-build contract for module.json, symbols and native headers."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_HEADER_KEY = "nativeUUIDHeader"
_REFERENCE_TOKEN = "@supportedBuild/"
_UUID = re.compile(r"^[0-9A-F]{8}(?:-[0-9A-F]{4}){3}-[0-9A-F]{12}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_DECIMAL = re.compile(r"^[1-9][0-9]*$")
_REQUIRED = {
    "architecture", "uuid", "steamBuildID",
    "originalExecutableSHA256", "referenceDirectory",
}
_OPTIONAL = {"bundleVersion", "contentBuildInfo", _HEADER_KEY}


def resolved_resource_source(value: str, build: dict | None) -> str:
    if not isinstance(value, str):
        raise ValueError("appResources source must be a string")
    if not value.startswith(_REFERENCE_TOKEN):
        return value
    if build is None:
        raise ValueError("appResources references supportedBuild without a declaration")
    relative = value[len(_REFERENCE_TOKEN):]
    if not relative or relative.startswith("/") or ".." in Path(relative).parts or "\\" in relative:
        raise ValueError("appResources supportedBuild reference is not contained")
    return build["referenceDirectory"].rstrip("/") + "/" + relative


def native_header(build: dict, *, game_name: str) -> str:
    if not isinstance(game_name, str) or not game_name or '"' in game_name or chr(92) in game_name:
        raise ValueError("native header game display name is invalid")
    raw = bytes.fromhex(build["uuid"].replace("-", ""))
    version = "1." + build["bundleVersion"] if "bundleVersion" in build else build["contentBuildInfo"]
    identity = f"{game_name} {version} {build['architecture']}"
    return (
        "/* GENERATED FROM module.json supportedBuild; regenerate with Tools/supported_build.py. */\n"
        "#ifndef MGT_SUPPORTED_BUILD_IDENTITY_H\n"
        "#define MGT_SUPPORTED_BUILD_IDENTITY_H\n"
        "#define MGT_SUPPORTED_GAME_UUID_BYTES "
        + ", ".join(f"0x{byte:02x}" for byte in raw) + "\n"
        + '#define MGT_SUPPORTED_GAME_DESCRIPTION "' + identity + '"\n'
        + "#endif\n"
    )


def validate_supported_build(module: Path, *, root: Path = ROOT, verify_generated: bool = True) -> dict | None:
    """Validate game-owned build identity without adding fields to Core's runtime manifest."""
    raw = json.loads(module.read_text(encoding="utf-8"))
    game_id = raw["id"]
    build = raw.get("supportedBuild")
    symbols_path = module.parent / "symbols.json"
    if build is None:
        if symbols_path.exists():
            raise ValueError(f"{game_id}: native symbols require supportedBuild")
        return None
    if not isinstance(build, dict) or not _REQUIRED <= build.keys() or build.keys() - (_REQUIRED | _OPTIONAL):
        raise ValueError(f"{game_id}: supportedBuild has missing or unknown fields")
    if build["architecture"] not in ("arm64", "x86_64") or not isinstance(build["uuid"], str) or not _UUID.fullmatch(build["uuid"]):
        raise ValueError(f"{game_id}: supportedBuild architecture/UUID is invalid")
    if not isinstance(build["steamBuildID"], str) or not _DECIMAL.fullmatch(build["steamBuildID"]):
        raise ValueError(f"{game_id}: supportedBuild steamBuildID is invalid")
    if not isinstance(build["originalExecutableSHA256"], str) or not _SHA256.fullmatch(build["originalExecutableSHA256"]):
        raise ValueError(f"{game_id}: supportedBuild original executable hash is invalid")
    if ("bundleVersion" in build) == ("contentBuildInfo" in build):
        raise ValueError(f"{game_id}: exactly one native build-version kind is required")
    key = "bundleVersion" if "bundleVersion" in build else "contentBuildInfo"
    if not isinstance(build[key], str) or not _DECIMAL.fullmatch(build[key]):
        raise ValueError(f"{game_id}: supportedBuild native build version is invalid")
    reference = build["referenceDirectory"]
    prefix = f"docs/reference/{game_id}"
    if not isinstance(reference, str) or not (reference == prefix or reference.startswith(prefix + "/")):
        raise ValueError(f"{game_id}: supportedBuild reference directory must be game-owned")
    parts = Path(reference)
    if parts.is_absolute() or ".." in parts.parts or "\\" in reference:
        raise ValueError(f"{game_id}: supportedBuild reference directory escapes the repository")
    resolved_root = root.resolve()
    directory = (root / parts).resolve()
    if not directory.is_dir() or resolved_root not in directory.parents:
        raise ValueError(f"{game_id}: supportedBuild reference directory is unavailable")

    if symbols_path.is_file():
        symbols = json.loads(symbols_path.read_text(encoding="utf-8"))
        for duplicate in ("uuid", "architecture", "steamBuildID", "bundleVersion", "contentBuildInfo"):
            if duplicate in symbols:
                raise ValueError(f"{game_id}: {duplicate} duplicated in symbols.json")

    terms = directory / "ui_terminology.json"
    if terms.is_file() and "bundleVersion" in build:
        target = json.loads(terms.read_text(encoding="utf-8")).get("target", {})
        if target.get("gameVersion") != "1." + build["bundleVersion"] or target.get("steamBuild") != build["steamBuildID"]:
            raise ValueError(f"{game_id}: terminology reference does not match supportedBuild")

    for item in raw.get("appResources", []):
        if not isinstance(item, dict) or not isinstance(item.get("source"), str):
            raise ValueError(f"{game_id}: invalid appResource declaration")
        resolved_resource_source(item["source"], build)

    header = build.get(_HEADER_KEY)
    if header is not None:
        if not isinstance(header, str) or not header.startswith("native/") or ".." in Path(header).parts or "\\" in header:
            raise ValueError(f"{game_id}: nativeUUIDHeader must be inside module/native")
        filename = (module.parent / header).resolve()
        if module.parent.resolve() not in filename.parents:
            raise ValueError(f"{game_id}: nativeUUIDHeader escapes its module")
        if verify_generated and (not filename.is_file() or filename.read_text(encoding="utf-8") != native_header(build, game_name=raw["displayName"])):
            raise ValueError(f"{game_id}: generated native UUID header differs from supportedBuild")
    return build


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-native-header", metavar="MODULE_ID")
    args = parser.parse_args()
    module_dir = ROOT / "Backend/games"
    modules = sorted(module_dir.glob("*/module.json"))
    if args.write_native_header:
        module = module_dir / args.write_native_header / "module.json"
        if module not in modules:
            parser.error("module manifest not found")
        build = validate_supported_build(module, verify_generated=False)
        if not build or _HEADER_KEY not in build:
            parser.error("module does not declare a generated native UUID header")
        filename = module.parent / build[_HEADER_KEY]
        filename.write_text(native_header(build, game_name=json.loads(module.read_text(encoding="utf-8"))["displayName"]), encoding="utf-8")
        print(filename.relative_to(ROOT).as_posix())
        return 0
    for module in modules:
        validate_supported_build(module)
    print("supported_builds_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
