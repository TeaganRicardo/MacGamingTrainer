#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

EXECUTABLE_REFERENCE_PREFIXES = ("docs/reference/hades2/",)


def is_executable_reference_data(path: str) -> bool:
    return path.startswith(EXECUTABLE_REFERENCE_PREFIXES) and not path.endswith(".md")


def is_docs_only(paths: list[str]) -> bool:
    normalized = [path.strip() for path in paths if path.strip()]
    if not normalized:
        return False
    return all(
        (path.startswith("docs/") or path.endswith(".md"))
        and not is_executable_reference_data(path)
        for path in normalized
    )


def changed_paths(base_sha: str, head_sha: str, cwd: Path | None = None) -> list[str]:
    if not base_sha or not head_sha or set(base_sha) == {"0"}:
        return []
    result = subprocess.run(
        ["git", "diff", "--no-renames", "--name-only", base_sha, head_sha, "--"],
        cwd=cwd,
        check=True,
        text=True,
        capture_output=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        raise SystemExit("usage: ci_docs_only.py BASE_SHA HEAD_SHA")
    paths = changed_paths(argv[1], argv[2])
    print("docs_only=true" if is_docs_only(paths) else "docs_only=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
