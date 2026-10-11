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


def command_text(command: Sequence[str]) -> str:
    result = subprocess.run(
        list(command),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
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


def xcode_identity() -> tuple[str, str]:
    lines = command_text(("xcodebuild", "-version")).splitlines()
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
    xcode_select_developer_dir = command_text(("xcode-select", "-p"))

    xcode_version, xcode_build = xcode_identity()
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
            "macOSVersion": command_text(("sw_vers", "-productVersion")),
            "macOSBuild": command_text(("sw_vers", "-buildVersion")),
        },
        "developer": {
            "requestedDeveloperDir": requested_developer_dir,
            "selectedDeveloperDir": selected_developer_dir,
            "xcodeSelectDeveloperDir": xcode_select_developer_dir,
            "xcodeVersion": xcode_version,
            "xcodeBuild": xcode_build,
            "sdk": {
                "name": "macosx",
                "path": command_text(("xcrun", "--sdk", "macosx", "--show-sdk-path")),
                "version": command_text(("xcrun", "--sdk", "macosx", "--show-sdk-version")),
                "build": command_text(("xcrun", "--sdk", "macosx", "--show-sdk-build-version")),
            },
            "swift": {
                "path": command_text(("xcrun", "--find", "swiftc")),
                "version": command_text(("xcrun", "swiftc", "--version")),
            },
            "clang": {
                "path": command_text(("xcrun", "--find", "clang")),
                "version": command_text(("xcrun", "clang", "--version")),
            },
            "lldb": {
                "path": command_text(("xcrun", "--find", "lldb")),
                "version": command_text(("xcrun", "lldb", "--version")),
                "pythonModulePath": command_text(("xcrun", "lldb", "-P")),
            },
            "xcodePython": {
                "path": command_text(("xcrun", "--find", "python3")),
                "version": command_text(("xcrun", "python3", "--version")),
            },
        },
    }


def main() -> int:
    try:
        print(json.dumps(collect_macos_toolchain(), indent=2, sort_keys=True))
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(error, file=os.sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
