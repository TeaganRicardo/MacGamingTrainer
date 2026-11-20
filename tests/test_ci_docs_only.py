import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "Tools/ci_docs_only.py"
REFERENCE_ROOT = "docs/reference/hades2/1.139672-24556151"
REFERENCE_DATA = f"{REFERENCE_ROOT}/catalog_legality.csv"
GENERATED_DATA = f"{REFERENCE_ROOT}/generated/loot.csv"
TERMINOLOGY_RESOURCE = json.loads((ROOT / "Backend/games/hades2/module.json").read_text())["supportedBuild"]["referenceDirectory"] + "/ui_terminology.json"

spec = importlib.util.spec_from_file_location("ci_docs_only", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

assert module.is_docs_only(["docs/reference/a.csv"])
assert module.is_docs_only(["PROJECT_STATUS.md", "docs/reference/a.csv"])
assert module.is_docs_only(["README.md", "AGENTS.md"])
assert module.is_docs_only(["docs/reference/hades2/README.md"])
assert not module.is_docs_only([])
assert not module.is_docs_only(["Backend/games/hades2/runtime/hades.lua"])
assert not module.is_docs_only(["docs/a.md", ".github/workflows/build2-macos.yml"])
assert not module.is_docs_only([REFERENCE_DATA])
assert not module.is_docs_only([f"{REFERENCE_ROOT}/manifest.json"])
assert not module.is_docs_only(["docs/a.md", REFERENCE_DATA])

MACOS_ONLY = {"test_hades2_run_log_watcher.py"}
DEPENDENCIES = module.load_macos_test_dependencies()


def assert_scope(paths, *, docs_only, linux, macos, module_build, build=None, full_build=None):
    expected_build = macos if build is None else build
    assert module.classify_scope(paths, macos_only_tests=MACOS_ONLY, test_dependencies=DEPENDENCIES) == {
        "docs_only": docs_only,
        "needs_linux": linux,
        "needs_macos": macos,
        "needs_module": module_build,
        "needs_build": expected_build,
        "needs_full_build": expected_build if full_build is None else full_build,
    }


assert_scope(
    ["README.md"],
    docs_only=True,
    linux=True,
    macos=False,
    module_build=False,
)
# Portable tests read documentation (VERSIONING.md, GAME_MODULES.md and the
# reference snapshots), so every documentation-only diff keeps the Linux lane.
tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, check=True, text=True, capture_output=True).stdout.split()
for document in [path for path in tracked if path.endswith(".md") or path.startswith("docs/")]:
    scope = module.classify_scope([document], macos_only_tests=MACOS_ONLY, test_dependencies=DEPENDENCIES)
    assert scope["needs_linux"], document
# Documentation is not a product build input, at any depth and in a mixed diff:
# a docs file next to code must not escalate the lane to the unified build.
for documentation in (
    "README.md", "ENGINEERING_INVARIANTS.md",
    "docs/development/lldb-fixture-lifetime.md",
):
    assert_scope(
        [documentation, "tests/test_hades2_run_log_watcher.py"],
        docs_only=False, linux=True, macos=True, module_build=False,
        build=False, full_build=False,
    )
assert_scope(
    ["docs/development/lldb-fixture-lifetime.md", "tests/test_ci_docs_only.py"],
    docs_only=False, linux=True, macos=False, module_build=False,
    build=False, full_build=False,
)
assert_scope(
    [],
    docs_only=False,
    linux=True,
    macos=True,
    module_build=True,
)
assert_scope(
    ["Backend/games/hades2/adapter.py"],
    docs_only=False,
    linux=True,
    macos=False,
    module_build=False,
)
assert_scope(
    ["Backend/games/hades/catalog.json"],
    docs_only=False,
    linux=True,
    macos=True,
    module_build=False,
    build=False,
)

for shared_backend_seam in (
    "Backend/core/__init__.py",
    "Backend/core/adapter.py",
    "Backend/core/module_manifest.py",
    "Backend/core/protocol.py",
    "Backend/core/registry.py",
    "Backend/core/server.py",
):
    assert_scope(
        [shared_backend_seam],
        docs_only=False,
        linux=True,
        macos=False,
        module_build=False,
    )

# Core Save implementation remains ordinary Backend/Core Python unless a
# separate packaging/platform boundary is touched.
assert_scope(
    ["Backend/core/save_service.py"],
    docs_only=False,
    linux=True,
    macos=False,
    module_build=False,
)
assert_scope(
    [REFERENCE_DATA],
    docs_only=False,
    linux=True,
    macos=False,
    module_build=False,
)
assert_scope(
    [TERMINOLOGY_RESOURCE],
    docs_only=False,
    linux=True,
    macos=True,
    module_build=False,
)
assert_scope(
    ["Sources/Hades2/Hades2Model.swift"],
    docs_only=False,
    linux=True,
    macos=True,
    module_build=False,
    full_build=False,
)
assert_scope(
    ["Sources/Core/UI/TrainerTheme.swift"],
    docs_only=False,
    linux=True,
    macos=True,
    module_build=True,
    full_build=False,
)
assert_scope(
    ["ContractFixtures/reference_module/backend/adapter.py"],
    docs_only=False,
    linux=True,
    macos=True,
    module_build=True,
)
assert_scope(
    ["Backend/games/hades2/module.json"],
    docs_only=False,
    linux=True,
    macos=True,
    module_build=False,
)
assert_scope(
    ["Backend/games/hades2/trainer-entitlements.plist"],
    docs_only=False,
    linux=True,
    macos=True,
    module_build=False,
)
assert_scope(
    ["tests/test_hades2_run_log_watcher.py"],
    docs_only=False,
    linux=True,
    macos=True,
    module_build=False,
    build=False,
)
assert_scope(
    ["tests/test_hades2_transport_outcome_unknown_taint.py"],
    docs_only=False,
    linux=True,
    macos=False,
    module_build=False,
)
for path in (
    "tests/hades2_lldb_worker_support.py", "tests/hades2_lldb_fixture.py",
    "tests/hades2_debugserver_owner.py",
    "Tools/test_inputs.py", "Tools/test_inventory.py",
):
    assert_scope([path], docs_only=False, linux=True, macos=True, module_build=False, build=False)
assert_scope(["tests/test_debugserver_ownership.py"],
             docs_only=False, linux=True, macos=False, module_build=False)
assert_scope(["tests/management_ui_harness.py"],
             docs_only=False, linux=True, macos=True, module_build=False, build=False)
assert_scope(["tests/native_picker_harness.py"],
             docs_only=False, linux=True, macos=True, module_build=False, build=False)
# The watchdog policy is a native fixture input, not a portable-only helper.
assert_scope(["tests/macos_fixture_policy.py"],
             docs_only=False, linux=True, macos=True, module_build=False, build=False)
# Coverage reporting interprets test metadata; it never builds the product.
assert_scope(["Tools/summarize_macos_coverage.py"],
             docs_only=False, linux=True, macos=False, module_build=False, build=False)
# Native test ownership must not classify the production controls as fixture
# support and thereby suppress the product compiler preflight.
for source in (
    "Sources/Core/UI/TrainerMotion.swift",
    "Sources/Core/UI/Primitives/TrainerToggleControl.swift",
    "Sources/Core/UI/Components/TrainerListControls.swift",
):
    assert_scope([source], docs_only=False, linux=True, macos=True,
                 module_build=True, build=True, full_build=False)

assert_scope(["tests/visual_hierarchy_harness.py"],
             docs_only=False, linux=True, macos=True, module_build=False, build=False)

# Native support ownership follows imports without loading any Python entrypoint.
with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    tests_root = root / "tests"
    tests_root.mkdir()
    native = tests_root / "test_native_fixture.py"
    native.write_text('MGT_PLATFORM = "macos"\nfrom fixture import sample\n')
    (tests_root / "fixture.py").write_text('from support import sample\n')
    (tests_root / "support.py").write_text('raise AssertionError("discovery must not run imports")\n')
    (tests_root / "test_portable.py").write_text("import fixture\n")
    assert module.load_macos_test_dependencies(root) == {
        "test_native_fixture.py": frozenset({"tests/fixture.py", "tests/support.py"}),
    }
    # The CLI classifier consumes the same graph, including deleted imports
    # that are still named by their native consumers at the head of the PR.
    (tests_root / "support.py").unlink()
    scope = module.classify_scope(
        ["tests/support.py"], root=root, reference_prefixes=(), app_resource_sources=(),
    )
    assert scope["needs_macos"] and not scope["needs_build"], scope
    for invalid in (
        '"tests/fixture.py"', '("../fixture.py",)', '("/fixture.py",)',
        '("./tests/fixture.py",)', '("tests/support.py",)',
    ):
        native.write_text(f'MGT_PLATFORM = "macos"\nMGT_INPUTS = {invalid}\n')
        try:
            module.load_macos_test_dependencies(root, changed_paths=["tests/support.py"])
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid native input declaration accepted: {invalid}")
assert_scope(
    ["Tools/supported_build.py"],
    docs_only=False,
    linux=True,
    macos=True,
    module_build=True,
)
assert_scope(
    ["Tools/ci_docs_only.py"],
    docs_only=False,
    linux=True,
    macos=False,
    module_build=False,
)

# Source identity determines platform work. Pure game logic is Linux-owned;
# Swift and native sources still require a real compiler, but isolated module
# verification is reserved for shared module/build boundaries.
assert_scope(["Backend/games/hades/runtime/hades.lua"], docs_only=False, linux=True, macos=False, module_build=False)
assert_scope(["Backend/games/hades2/native/CommandMailbox.c"], docs_only=False, linux=True, macos=True, module_build=False)
# Declaring a product input as a native-test dependency routes that test; it
# must not turn the input into fixture support that skips the product build.
assert_scope(["Backend/games/hades2/native/EffectBlockQuery.c"], docs_only=False, linux=True, macos=True, module_build=False)
assert_scope(["Tools/clean_signing_metadata.py"], docs_only=False, linux=True, macos=True, module_build=True)
assert_scope(["Tools/resident_runtime.py"], docs_only=False, linux=True, macos=True, module_build=False)
assert_scope(["Sources/Hades/HadesModule.swift"], docs_only=False, linux=True, macos=True, module_build=False, full_build=False)
assert_scope(["Tools/run_macos_checks.sh"], docs_only=False, linux=True, macos=True, module_build=False, build=False)
assert_scope([".github/workflows/direct-release.yml"], docs_only=False, linux=True, macos=False, module_build=False)
assert_scope(["Tools/select_macos_pr_tests.py"], docs_only=False, linux=True, macos=True, module_build=False, build=False)
assert_scope([".github/workflows/module-build-matrix.yml"], docs_only=False, linux=True, macos=False, module_build=True, build=False)
assert_scope(["Tools/profile_hades2_operations.py"], docs_only=False, linux=True, macos=False, module_build=False)
assert_scope(["tests/fixtures/swift/InMemoryDefaults.swift"], docs_only=False, linux=True, macos=True, module_build=False, build=False)
assert_scope(["Backend/core/native/example.c"], docs_only=False, linux=True, macos=True, module_build=False)
assert_scope(["Backend/games/example/unknown.binary"], docs_only=False, linux=True, macos=True, module_build=False)

# Full builds are mandatory for every link, ABI and distribution boundary.
# Multiple changed paths use the strictest decision, never the fastest path.
assert_scope(["Sources/App.swift"], docs_only=False, linux=True, macos=True, module_build=True)
assert_scope(["Info.plist"], docs_only=False, linux=True, macos=True, module_build=False)
assert_scope(["app.json"], docs_only=False, linux=True, macos=True, module_build=True)
assert_scope(["build.sh"], docs_only=False, linux=True, macos=True, module_build=True)
assert_scope(
    [".github/workflows/build2-macos.yml"],
    docs_only=False,
    linux=True,
    macos=True,
    module_build=False,
    build=False,
    full_build=False,
)
assert_scope(
    [".github/workflows/build2-macos.yml", "build.sh"],
    docs_only=False,
    linux=True,
    macos=True,
    module_build=True,
    build=True,
    full_build=True,
)
assert_scope(["Tools/python_runtime.json"], docs_only=False, linux=True, macos=True, module_build=True)
assert_scope(["Sources/Hades2/Hades2Model.swift", "Backend/games/hades/runtime.lua"],
             docs_only=False, linux=True, macos=True, module_build=False, full_build=False)
assert_scope(["Sources/Hades2/Hades2Model.swift", "Info.plist"],
             docs_only=False, linux=True, macos=True, module_build=False)

# Reference ownership comes from module identity, and macOS routing for a
# reference file comes from appResources rather than a filename convention.
synthetic_prefixes = module.executable_reference_prefixes(("alpha", "beta"))
assert not module.is_docs_only(
    ["docs/reference/alpha/catalog.csv"],
    reference_prefixes=synthetic_prefixes,
)
assert module.is_docs_only(
    ["docs/reference/gamma/catalog.csv"],
    reference_prefixes=synthetic_prefixes,
)
assert module.classify_scope(
    ["docs/reference/alpha/catalog.csv"],
    macos_only_tests=MACOS_ONLY,
    reference_prefixes=synthetic_prefixes,
    app_resource_sources=(),
) == {
    "docs_only": False,
    "needs_linux": True,
    "needs_macos": False,
    "needs_module": False,
    "needs_build": False,
    "needs_full_build": False,
}
assert module.classify_scope(
    ["docs/reference/alpha/anything.json"],
    macos_only_tests=MACOS_ONLY,
    reference_prefixes=synthetic_prefixes,
    app_resource_sources=("docs/reference/alpha/anything.json",),
) == {
    "docs_only": False,
    "needs_linux": True,
    "needs_macos": True,
    "needs_module": False,
    "needs_build": True,
    "needs_full_build": True,
}


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True)


def head(root: Path) -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()


def commit_all(root: Path, message: str) -> str:
    git(root, "add", "-A")
    git(root, "commit", "-qm", message)
    return head(root)


with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    git(root, "init", "-q")
    git(root, "config", "user.email", "ci@example.invalid")
    git(root, "config", "user.name", "CI")

    reference = root / REFERENCE_DATA
    generated = root / GENERATED_DATA
    docs_note = root / "docs/a.md"
    reference.parent.mkdir(parents=True)
    docs_note.parent.mkdir(parents=True, exist_ok=True)
    reference.write_text("id,kind\nZeusUpgrade,loot\n")
    docs_note.write_text("notes\n")
    commit_all(root, "base")

    # Modification of executable reference data must run normal checks.
    base = head(root)
    reference.write_text("id,kind\nZeusUpgrade,loot\nHeraUpgrade,loot\n")
    current = commit_all(root, "modify reference")
    paths = module.changed_paths(base, current, root)
    assert paths == [REFERENCE_DATA], paths
    assert not module.is_docs_only(paths)

    # Deletion retains the executable reference path in the diff.
    base = current
    reference.unlink()
    current = commit_all(root, "delete reference")
    paths = module.changed_paths(base, current, root)
    assert paths == [REFERENCE_DATA], paths
    assert not module.is_docs_only(paths)

    # Addition of generated executable reference data must run normal checks.
    base = current
    generated.parent.mkdir(parents=True)
    generated.write_text("id\nZeusUpgrade\n")
    current = commit_all(root, "add generated reference")
    paths = module.changed_paths(base, current, root)
    assert paths == [GENERATED_DATA], paths
    assert not module.is_docs_only(paths)

    # Mixed documentation + executable data changes must run normal checks.
    base = current
    generated.write_text("id\nZeusUpgrade\nHeraUpgrade\n")
    docs_note.write_text("updated notes\n")
    current = commit_all(root, "mixed docs and reference")
    paths = module.changed_paths(base, current, root)
    assert set(paths) == {GENERATED_DATA, "docs/a.md"}, paths
    assert not module.is_docs_only(paths)

    # --no-renames preserves the old executable path when data moves into a
    # docs-only location, so routing cannot miss the change by seeing only the new path.
    base = current
    git(root, "mv", GENERATED_DATA, "docs/archived-loot.csv")
    current = commit_all(root, "move reference out")
    paths = module.changed_paths(base, current, root)
    assert set(paths) == {GENERATED_DATA, "docs/archived-loot.csv"}, paths
    assert not module.is_docs_only(paths)

    # Ordinary documentation still takes the fast path.
    base = current
    docs_note.write_text("documentation only\n")
    current = commit_all(root, "docs only")
    paths = module.changed_paths(base, current, root)
    assert paths == ["docs/a.md"], paths
    assert module.is_docs_only(paths)

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "ci@example.invalid")
    git(root, "config", "user.name", "CI")

    (root / "README.md").write_text("base\n")
    initial = commit_all(root, "base")
    git(root, "branch", "feature", initial)

    main_only = root / "Backend/main_only.py"
    main_only.parent.mkdir(parents=True)
    main_only.write_text("x = 1\n")
    main_tip = commit_all(root, "main-only change")

    git(root, "checkout", "-q", "feature")
    feature_doc = root / "docs/feature.md"
    feature_doc.parent.mkdir(parents=True)
    feature_doc.write_text("feature docs\n")
    feature_tip = commit_all(root, "feature docs")

    # PR scope is merge-base..head, not a tip-to-tip tree comparison. A change
    # that exists only on a newer base branch must not contaminate the PR scope.
    paths = module.changed_paths(main_tip, feature_tip, root)
    assert paths == ["docs/feature.md"], paths
    assert module.is_docs_only(paths)

# Darwin target probe and LLDB/transport Backend modules run macOS checks, while
# the pure-Python wire protocol stays on Linux fast path.
for darwin_backend in (
    "Backend/core/target_probe.py",
    "Backend/core/process_time_warp.py",
    "Backend/debugger/lldb_time_warp.py",
    "Backend/games/hades2/transport.py",
):
    scope = module.classify_scope([darwin_backend])
    assert scope["needs_macos"] is True, (darwin_backend, scope)
assert module.classify_scope(["Backend/core/protocol.py"])["needs_macos"] is False

# Workflow dispatch and the nightly schedule have no PR diff base, so the
# workflow passes an empty BASE_SHA. That is unknown scope, which the scope job's
# own command line must route to every lane rather than to a fast path. A new
# branch's all-zero base is unknown scope too.
current_head = head(ROOT)
for base in ("", "0" * 40):
    emitted = subprocess.run(
        [sys.executable, str(SCRIPT), base, current_head],
        cwd=ROOT, check=True, text=True, capture_output=True,
    ).stdout.split()
    assert emitted == [
        "docs_only=false", "needs_linux=true", "needs_macos=true",
        "needs_module=true", "needs_build=true", "needs_full_build=true",
    ], (base, emitted)

print("ci_docs_only_ok")
