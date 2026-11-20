#!/usr/bin/env python3
"""Select macOS PR tests from their source and helper inputs."""
from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from ci_docs_only import changed_paths
from module_inventory import MODULES_RELATIVE, discover_module_ids
from product_support import CORE_SWIFT_SOURCES
from supported_build import resolved_resource_source
from test_inputs import affected_tests, is_native_fixture, load_macos_test_dependencies
from test_inventory import ROOT

BUILD_SMOKE = "test_build_signing_metadata_macos.py"

# Journeys that assert native focus, key-window and foreground activation state.
# A hosted runner cannot guarantee that a background test process becomes the
# active application, and macOS activation is cooperative: the wait then expires
# even though the product is correct. They stay in the convergence inventory and
# run against an exact SHA there (explicit dispatch, and nightly on main);
# gating every PR on them only produced non-deterministic red results.
@dataclass(frozen=True)
class Deferral:
    """Why a native journey is absent from the PR lane, and who verifies it."""

    reason: str
    verification_owner: str


CONVERGENCE_OWNER = "Build 2 macOS convergence: workflow_dispatch on the exact SHA, and nightly on main"

PR_DEFERRED: dict[str, Deferral] = {
    "test_hades2_view_state_flow.py": Deferral(
        reason="asserts native focus, key-window and foreground activation",
        verification_owner=CONVERGENCE_OWNER,
    ),
    "test_multi_game_contexts.py": Deferral(
        reason="drives two real module adapters through foreground activation",
        verification_owner=CONVERGENCE_OWNER,
    ),
    "test_runtime_text_edit_completion.py": Deferral(
        reason="requires a focused native field editor in the foreground",
        verification_owner=CONVERGENCE_OWNER,
    ),
}


@dataclass(frozen=True)
class MacOSTestRouting:
    tests: set[str]
    dependencies: dict[str, frozenset[str]]
    sources: dict[str, str]
    app_modules: tuple[str, ...]

    def relevant_tests(self, paths: list[str]) -> list[str]:
        if not paths:
            return sorted(self.tests)

        chosen = affected_tests(paths, self.dependencies)
        chosen.update(path.removeprefix("tests/") for path in paths if path.startswith("tests/"))
        chosen.intersection_update(self.tests)

        core_changed = any(path.startswith(f"{CORE_SWIFT_SOURCES}/") for path in paths)
        for game, directory in self.sources.items():
            if not (core_changed and game in self.app_modules
                    or any(path.startswith(directory) for path in paths)):
                continue
            smoke = module_smoke_tests(game, self.tests)
            if not smoke:
                raise ValueError(f"{game}: no macOS behavior smoke entry in the inventory")
            if not smoke - PR_DEFERRED.keys():
                raise ValueError(f"{game}: every module behavior smoke entry is deferred; declare a stable PR owner")
            chosen.update(smoke)
        if any(is_native_fixture(path) for path in paths):
            return sorted(self.tests)
        return sorted(chosen)

    def selection(self, paths: list[str]) -> dict:
        relevant = self.relevant_tests(paths)
        selected = [name for name in relevant if name not in PR_DEFERRED]
        return {
            "relevant": relevant,
            "selected": selected,
            "deferred": {name: asdict(PR_DEFERRED[name]) for name in relevant if name in PR_DEFERRED},
            "requirements": {"lua52_native": any(
                "tests/lua_native_prerequisites.py" in self.dependencies[name] for name in selected
            )},
        }


def module_smoke_tests(game: str, tests: set[str]) -> set[str]:
    names = {f"test_{game}_{suffix}.py" for suffix in ("model_flow", "view_state_flow", "frontend")}
    return {test for test in tests if test.rsplit("/", 1)[-1] in names}


def load_routing(root: Path = ROOT, *, changed: list[str] | tuple[str, ...] = ()) -> MacOSTestRouting:
    manifests = {}
    sources = {}
    for game in discover_module_ids(root):
        manifest_path = MODULES_RELATIVE / game / "module.json"
        manifest = json.loads((root / manifest_path).read_text(encoding="utf-8"))
        source = manifest.get("frontend", {}).get("sourceDirectory")
        if not isinstance(source, str) or not source.startswith("Sources/"):
            raise ValueError(f"{game}: missing frontend sourceDirectory")
        manifests[game] = manifest_path.as_posix(), manifest
        sources[game] = source.rstrip("/") + "/"

    app = json.loads((root / "app.json").read_text(encoding="utf-8"))
    games = app.get("modules") if isinstance(app, dict) else None
    if not isinstance(games, list) or not games or any(
        not isinstance(game, str) or game not in sources for game in games
    ) or len(set(games)) != len(games):
        raise ValueError("app.json modules must be a non-empty array of unique, declared game IDs")
    dependencies = load_macos_test_dependencies(root, source_dirs=sources, changed_paths=changed)
    if not dependencies:
        raise ValueError("no macOS tests discovered")
    tests = set(dependencies)
    for game, (manifest_path, manifest) in manifests.items():
        runtime_inputs = {manifest_path} | {
            resolved_resource_source(resource["source"], manifest.get("supportedBuild"))
            for resource in manifest.get("appResources", [])
        }
        consumers = module_smoke_tests(game, tests) | affected_tests([manifest_path], dependencies)
        for name in consumers:
            dependencies[name] |= runtime_inputs
        entitlements = manifest.get("buildRequirements", {}).get("entitlements")
        if entitlements and BUILD_SMOKE in tests:
            dependencies[BUILD_SMOKE] |= {entitlements}
    return MacOSTestRouting(tests, dependencies, sources, tuple(games))


def main(argv: list[str]) -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_sha")
    parser.add_argument("head_sha")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv[1:])
    try:
        paths = changed_paths(args.base_sha, args.head_sha)
        selection = load_routing(changed=paths).selection(paths)
        if args.output:
            args.output.write_text(json.dumps(selection, sort_keys=True) + "\n", encoding="utf-8")
    except (OSError, SyntaxError, ValueError, RuntimeError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        print(f"macOS PR selection failed: {exc}", file=sys.stderr)
        return 2
    print("\n".join(selection["selected"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
