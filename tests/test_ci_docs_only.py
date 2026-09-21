from pathlib import Path
import importlib.util
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "Tools/ci_docs_only.py"

spec = importlib.util.spec_from_file_location("ci_docs_only", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

assert module.is_docs_only(["docs/reference/a.csv"])
assert module.is_docs_only(["PROJECT_STATUS.md", "docs/reference/a.csv"])
assert module.is_docs_only(["README.md", "AGENTS.md"])
assert not module.is_docs_only([])
assert not module.is_docs_only(["Backend/games/hades2/runtime/hades.lua"])
assert not module.is_docs_only(["docs/a.md", ".github/workflows/build2-macos.yml"])

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "ci@example.invalid"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "CI"], cwd=root, check=True)

    (root / "Backend").mkdir()
    (root / "Backend" / "code.py").write_text("x = 1\n")
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=root, check=True)
    base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()

    (root / "docs").mkdir()
    subprocess.run(["git", "mv", "Backend/code.py", "docs/code.md"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "rename"], cwd=root, check=True)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()

    paths = module.changed_paths(base, head, root)
    assert set(paths) == {"Backend/code.py", "docs/code.md"}, paths
    assert not module.is_docs_only(paths)

print("ci_docs_only_ok")
