#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
from typing import Mapping, Sequence


SUPPORTED_RUNNER_LABEL = "macos-26"
SUPPORTED_RUNNER_ARCH = "ARM64"
SUPPORTED_DEVELOPER_DIR = "/Applications/Xcode_26.6.app/Contents/Developer"
SUPPORTED_XCODE_VERSION = "26.6"
SUPPORTED_XCODE_BUILD = "17F113"


def require_env(env: Mapping[str, str], name: str) -> str:
    value = env.get(name, "").strip()
    if not value:
        raise RuntimeError(f"missing required environment variable: {name}")
    return value


def command_text(command: Sequence[str], env: Mapping[str, str] | None = None) -> str:
    result = subprocess.run(
        list(command),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        env=None if env is None else dict(env),
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(
            f"toolchain command failed ({' '.join(command)}): {detail or result.returncode}"
        )
    value = (result.stdout or result.stderr).strip()
    if not value:
        raise RuntimeError(f"toolchain command returned no identity: {' '.join(command)}")
    return value


def xcode_identity(env: Mapping[str, str] | None = None) -> tuple[str, str]:
    lines = command_text(("xcodebuild", "-version"), env).splitlines()
    if len(lines) < 2 or not lines[0].startswith("Xcode ") or not lines[1].startswith("Build version "):
        raise RuntimeError("unexpected xcodebuild -version output")
    return lines[0][len("Xcode "):].strip(), lines[1][len("Build version "):].strip()


def collect_macos_toolchain(env: Mapping[str, str] | None = None) -> dict[str, object]:
    env = os.environ if env is None else env
    runner_label = require_env(env, "MGT_MACOS_RUNNER_LABEL")
    runner_os = require_env(env, "RUNNER_OS")
    runner_arch = require_env(env, "RUNNER_ARCH")
    image_os = require_env(env, "ImageOS")
    image_version = require_env(env, "ImageVersion")
    requested_developer_dir = require_env(env, "DEVELOPER_DIR")

    if runner_label != SUPPORTED_RUNNER_LABEL:
        raise RuntimeError(
            f"unsupported macOS runner label {runner_label!r}; expected {SUPPORTED_RUNNER_LABEL!r}"
        )
    if runner_os != "macOS":
        raise RuntimeError(f"macOS toolchain verification requires RUNNER_OS=macOS, got {runner_os!r}")
    if runner_arch != SUPPORTED_RUNNER_ARCH:
        raise RuntimeError(
            f"unsupported macOS runner architecture {runner_arch!r}; expected {SUPPORTED_RUNNER_ARCH!r}"
        )
    if requested_developer_dir != SUPPORTED_DEVELOPER_DIR:
        raise RuntimeError(
            "unsupported DEVELOPER_DIR "
            f"{requested_developer_dir!r}; expected {SUPPORTED_DEVELOPER_DIR!r}"
        )

    # DEVELOPER_DIR is the explicit selection consumed by xcrun/xcodebuild.
    # Record xcode-select's host default separately because GitHub may change it
    # independently of the workflow-selected toolchain.
    selected_developer_dir = requested_developer_dir
    xcode_select_developer_dir = command_text(("xcode-select", "-p"), env)

    xcode_version, xcode_build = xcode_identity(env)
    if xcode_version != SUPPORTED_XCODE_VERSION or xcode_build != SUPPORTED_XCODE_BUILD:
        raise RuntimeError(
            "unsupported Xcode identity "
            f"{xcode_version} ({xcode_build}); expected "
            f"{SUPPORTED_XCODE_VERSION} ({SUPPORTED_XCODE_BUILD})"
        )

    return {
        "host": {
            "runnerLabel": runner_label,
            "runnerOS": runner_os,
            "runnerArch": runner_arch,
            "imageOS": image_os,
            "imageVersion": image_version,
            # GitHub-hosted images are serviced in place. The exact image
            # version is retained above; this field prevents consumers from
            # mistaking the selected YAML label for a hermetic VM image.
            "imageMutable": True,
            "macOSVersion": command_text(("sw_vers", "-productVersion"), env),
            "macOSBuild": command_text(("sw_vers", "-buildVersion"), env),
        },
        "developer": {
            "requestedDeveloperDir": requested_developer_dir,
            "selectedDeveloperDir": selected_developer_dir,
            "xcodeSelectDeveloperDir": xcode_select_developer_dir,
            "xcodeVersion": xcode_version,
            "xcodeBuild": xcode_build,
            "sdk": {
                "name": "macosx",
                "path": command_text(("xcrun", "--sdk", "macosx", "--show-sdk-path"), env),
                "version": command_text(("xcrun", "--sdk", "macosx", "--show-sdk-version"), env),
                "build": command_text(("xcrun", "--sdk", "macosx", "--show-sdk-build-version"), env),
            },
            "swift": {
                "path": command_text(("xcrun", "--find", "swiftc"), env),
                "version": command_text(("xcrun", "swiftc", "--version"), env),
            },
            "clang": {
                "path": command_text(("xcrun", "--find", "clang"), env),
                "version": command_text(("xcrun", "clang", "--version"), env),
            },
            "lldb": {
                "path": command_text(("xcrun", "--find", "lldb"), env),
                "version": command_text(("xcrun", "lldb", "--version"), env),
                "pythonModulePath": command_text(("xcrun", "lldb", "-P"), env),
            },
            "xcodePython": {
                "path": command_text(("xcrun", "--find", "python3"), env),
                "version": command_text(("xcrun", "python3", "--version"), env),
            },
        },
    }


def verify_recorded_macos_toolchain(toolchain: object) -> None:
    if not isinstance(toolchain, dict):
        raise RuntimeError("provenance macOS toolchain must be an object")
    host = toolchain.get("host")
    developer = toolchain.get("developer")
    if not isinstance(host, dict) or not isinstance(developer, dict):
        raise RuntimeError("provenance macOS toolchain is missing host/developer identity")

    expected_host = {
        "runnerLabel": SUPPORTED_RUNNER_LABEL,
        "runnerOS": "macOS",
        "runnerArch": SUPPORTED_RUNNER_ARCH,
        "imageMutable": True,
    }
    for field, expected in expected_host.items():
        if host.get(field) != expected:
            raise RuntimeError(f"provenance host {field} differs from supported identity")
    for field in ("imageOS", "imageVersion", "macOSVersion", "macOSBuild"):
        if not isinstance(host.get(field), str) or not host[field].strip():
            raise RuntimeError(f"provenance host {field} is missing")

    expected_developer = {
        "selectedDeveloperDir": SUPPORTED_DEVELOPER_DIR,
        "xcodeVersion": SUPPORTED_XCODE_VERSION,
        "xcodeBuild": SUPPORTED_XCODE_BUILD,
    }
    for field, expected in expected_developer.items():
        if developer.get(field) != expected:
            raise RuntimeError(f"provenance developer {field} differs from supported identity")
    if developer.get("requestedDeveloperDir") != developer.get("selectedDeveloperDir"):
        raise RuntimeError("provenance requested and selected developer directories differ")
    if not isinstance(developer.get("xcodeSelectDeveloperDir"), str) or not developer["xcodeSelectDeveloperDir"].strip():
        raise RuntimeError("provenance xcode-select developer directory is missing")

    required_fields = {
        "sdk": ("name", "path", "version", "build"),
        "swift": ("path", "version"),
        "clang": ("path", "version"),
        "lldb": ("path", "version", "pythonModulePath"),
        "xcodePython": ("path", "version"),
    }
    for owner, fields in required_fields.items():
        identity = developer.get(owner)
        if not isinstance(identity, dict):
            raise RuntimeError(f"provenance developer {owner} identity is missing")
        for field in fields:
            value = identity.get(field)
            if not isinstance(value, str) or not value.strip():
                raise RuntimeError(f"provenance developer {owner}.{field} is missing")
    if developer["sdk"]["name"] != "macosx":
        raise RuntimeError("provenance SDK identity is not macosx")


def main() -> int:
    try:
        print(json.dumps(collect_macos_toolchain(), indent=2, sort_keys=True))
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(error, file=os.sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
