#!/usr/bin/env python3
"""Select an immutable release tag from published source identities.

Official three-part tags own prior bundle build numbers; the legacy v0.1 tag
is historical and is intentionally excluded from the modern release policy.
"""
from __future__ import annotations

import argparse
import plistlib
import re
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

_SEMVER = r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
_VERSION = re.compile(rf"^{_SEMVER}$")
_RELEASE_TAG = re.compile(rf"^v(?P<version>{_SEMVER})(?:\+b(?P<build>[1-9][0-9]*))?$")
_BUILD = re.compile(r"^[1-9][0-9]*$")


def published_builds(repo_root: Path) -> dict[str, int]:
    """Read each official tag's actual plist; never trust the tag suffix alone."""
    tags = subprocess.run(
        ["git", "tag", "--list"], cwd=repo_root, check=True,
        capture_output=True, text=True,
    ).stdout.splitlines()
    published = {}
    for tag in tags:
        match = _RELEASE_TAG.fullmatch(tag)
        if match is None:
            continue
        source = subprocess.run(
            ["git", "show", f"{tag}:Info.plist"], cwd=repo_root,
            check=True, capture_output=True,
        ).stdout
        metadata = plistlib.loads(source)
        build = metadata.get("CFBundleVersion")
        if metadata.get("CFBundleShortVersionString") != match.group("version"):
            raise ValueError(f"{tag}: source product version differs from its release tag")
        if not isinstance(build, str) or _BUILD.fullmatch(build) is None:
            raise ValueError(f"{tag}: source bundle build is invalid")
        number = int(build)
        if match.group("build") is not None and number != int(match.group("build")):
            raise ValueError(f"{tag}: source bundle build differs from its +b tag")
        published[tag] = number
    return published


def select_release_tag(version: str, build: str, published: Mapping[str, int]) -> str:
    """Reserve a new tag only for a bundle build newer than *every* release."""
    if _VERSION.fullmatch(version) is None:
        raise ValueError("product release version must be three-part SemVer")
    if _BUILD.fullmatch(build) is None:
        raise ValueError("bundle build must be a positive integer")

    base = f"v{version}"
    if base not in published and any(tag.startswith(base + "+b") for tag in published):
        raise ValueError(f"{base}: base release tag is missing but later builds already exist")
    candidate = f"{base}+b{build}" if base in published else base
    if candidate in published:
        raise ValueError(f"release tag {candidate} already exists; refusing replacement")

    if published:
        prior_tag, prior_build = max(published.items(), key=lambda entry: entry[1])
        if int(build) <= prior_build:
            raise ValueError(
                f"bundle build {build} must exceed previous published build "
                f"{prior_build} ({prior_tag}), including across product versions"
            )
    return candidate


def _plist_release_identity(plist_bytes: bytes) -> tuple[str, str]:
    metadata = plistlib.loads(plist_bytes)
    if not isinstance(metadata, dict):
        raise ValueError("Info.plist root must be a plist dictionary")
    version = metadata.get("CFBundleShortVersionString")
    build = metadata.get("CFBundleVersion")
    if not isinstance(version, str) or not isinstance(build, str):
        raise ValueError("Info.plist release identity must contain string CFBundleShortVersionString and CFBundleVersion")
    return version, build


def release_identity_changed(repo_root: Path, base_ref: str, head_ref: str = "HEAD") -> bool:
    """Return True unless both refs parse cleanly and carry identical version/build."""
    head_bytes = subprocess.run(
        ["git", "show", f"{head_ref}:Info.plist"], cwd=repo_root,
        check=True, capture_output=True,
    ).stdout
    head_identity = _plist_release_identity(head_bytes)

    effective_base = base_ref if base_ref and not set(base_ref) == {"0"} else f"{head_ref}^"
    prior = subprocess.run(
        ["git", "show", f"{effective_base}:Info.plist"], cwd=repo_root,
        capture_output=True,
    )
    if prior.returncode != 0:
        return True  # Fail closed when base history is unavailable (e.g. root commit).
    try:
        base_identity = _plist_release_identity(prior.stdout)
    except (ValueError, plistlib.InvalidFileException):
        return True
    return base_identity != head_identity


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", nargs="?")
    parser.add_argument("build", nargs="?")
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--push-precheck", nargs=2, metavar=("BASE", "HEAD"))
    args = parser.parse_args()
    try:
        if args.push_precheck:
            if args.version is not None or args.build is not None:
                parser.error("--push-precheck does not accept positional version/build arguments")
            base_ref, head_ref = args.push_precheck
            changed = release_identity_changed(args.repo_root, base_ref, head_ref)
            if not changed:
                print(
                    "Info.plist CFBundleShortVersionString and CFBundleVersion are unchanged; skipping release.",
                    file=sys.stderr,
                )
            print("true" if changed else "false")
            return 0
        if not args.version or not args.build:
            parser.error("version and build are required unless --push-precheck is specified")
        print(select_release_tag(args.version, args.build, published_builds(args.repo_root)))
    except (OSError, ValueError, plistlib.InvalidFileException, subprocess.CalledProcessError) as error:
        print(f"Release identity rejected: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
