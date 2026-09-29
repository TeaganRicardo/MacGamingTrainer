import importlib.util
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "Tools/ci_docs_only.py"
REFERENCE_ROOT = "docs/reference/hades2/1.139672-24556151"
REFERENCE_DATA = f"{REFERENCE_ROOT}/catalog_legality.csv"
GENERATED_DATA = f"{REFERENCE_ROOT}/generated/loot.csv"
TERMINOLOGY_RESOURCE = f"{REFERENCE_ROOT}/ui_terminology.json"

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


def assert_scope(paths, *, docs_only, linux, macos, module_build):
    assert module.classify_scope(paths, macos_only_tests=MACOS_ONLY) == {
        "docs_only": docs_only,
        "needs_linux": linux,
        "needs_macos": macos,
        "needs_module": module_build,
    }


assert_scope(
    ["README.md"],
    docs_only=True,
    linux=False,
    macos=False,
    module_build=False,
)
assert_scope(
    ["Backend/games/hades2/adapter.py"],
    docs_only=False,
    linux=True,
    macos=False,
    module_build=False,
)

for shared_backend_seam in (
    "Backend/core/__init__.py",
    "Backend/core/adapter.py",
    "Backend/core/game_spec.py",
    "Backend/core/module_manifest.py",
    "Backend/core/protocol.py",
    "Backend/core/registry.py",
    "Backend/core/server.py",
):
    assert_scope(
        [shared_backend_seam],
        docs_only=False,
        linux=True,
        macos=True,
        module_build=True,
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
)
assert_scope(
    ["Sources/Core/UI/TrainerTheme.swift"],
    docs_only=False,
    linux=True,
    macos=True,
    module_build=True,
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
    module_build=True,
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
)
assert_scope(
    ["tests/test_hades2_transport_outcome_unknown_taint.py"],
    docs_only=False,
    linux=True,
    macos=False,
    module_build=False,
)
assert_scope(
    ["Tools/ci_docs_only.py"],
    docs_only=False,
    linux=True,
    macos=True,
    module_build=True,
)

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

print("ci_docs_only_ok")
