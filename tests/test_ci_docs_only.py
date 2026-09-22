from pathlib import Path
import importlib.util
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "Tools/ci_docs_only.py"
REFERENCE_ROOT = "docs/reference/hades2/1.139672-24556151"
REFERENCE_DATA = f"{REFERENCE_ROOT}/catalog_legality.csv"
GENERATED_DATA = f"{REFERENCE_ROOT}/generated/loot.csv"

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

print("ci_docs_only_ok")
