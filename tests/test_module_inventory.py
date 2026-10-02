from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Tools"))

from module_inventory import (
    ModuleInventoryError,
    app_resource_sources_for_diff,
    current_app_resource_sources,
    discover_module_ids,
    executable_reference_prefixes,
    module_ids_for_diff,
)


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def commit(root: Path, message: str) -> str:
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", message], cwd=root, check=True)
    return git(root, "rev-parse", "HEAD")


def write_module(
    root: Path,
    game_id: str,
    *,
    declared_id: str | None = None,
    app_resources=(),
) -> None:
    module_dir = root / "Backend/games" / game_id
    module_dir.mkdir(parents=True, exist_ok=True)
    (module_dir / "module.json").write_text(
        json.dumps({
            "id": declared_id or game_id,
            "appResources": [
                {"source": source, "destination": Path(source).name}
                for source in app_resources
            ],
        }) + "\n",
        encoding="utf-8",
    )


# Working-tree discovery is deterministic and game-agnostic.
with tempfile.TemporaryDirectory(prefix="mgt-module-inventory-") as temporary:
    root = Path(temporary)
    write_module(root, "beta", app_resources=("docs/reference/beta/ui.json",))
    write_module(root, "alpha", app_resources=("docs/reference/alpha/catalog.csv",))
    assert discover_module_ids(root) == ("alpha", "beta")
    assert executable_reference_prefixes(discover_module_ids(root)) == (
        "docs/reference/alpha/",
        "docs/reference/beta/",
    )
    assert current_app_resource_sources(root) == (
        "docs/reference/alpha/catalog.csv",
        "docs/reference/beta/ui.json",
    )

# A nested manifest is not a production module layout. Discovery and the
# build loader must agree on the same Backend/games/<id>/module.json boundary.
with tempfile.TemporaryDirectory(prefix="mgt-module-inventory-nested-") as temporary:
    root = Path(temporary)
    nested = root / "Backend/games/group/alpha"
    nested.mkdir(parents=True)
    (nested / "module.json").write_text('{"id":"alpha"}\n', encoding="utf-8")
    try:
        discover_module_ids(root)
    except ModuleInventoryError as error:
        assert "directly under Backend/games" in str(error), error
    else:
        raise AssertionError("nested module manifest was accepted")


# A manifest cannot claim a different identity from its directory. Shared
# tooling must fail closed rather than silently discover one name and build
# another.
with tempfile.TemporaryDirectory(prefix="mgt-module-inventory-bad-id-") as temporary:
    root = Path(temporary)
    write_module(root, "alpha", declared_id="beta")
    try:
        discover_module_ids(root)
    except ModuleInventoryError as error:
        assert "must match directory" in str(error), error
    else:
        raise AssertionError("module id/directory mismatch was accepted")

# Diff discovery deliberately takes the union of merge-base and head. Removing
# a module cannot make executable reference data under docs/reference/<id> turn
# into docs-only content in the same commit that removes its owner.
with tempfile.TemporaryDirectory(prefix="mgt-module-inventory-diff-") as temporary:
    root = Path(temporary)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "ci@example.invalid"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "CI"], cwd=root, check=True)

    write_module(root, "alpha", app_resources=("docs/reference/alpha/data.json",))
    write_module(root, "beta", app_resources=("Sources/Beta/table.json",))
    reference = root / "docs/reference/alpha/data.json"
    reference.parent.mkdir(parents=True)
    reference.write_text("{}\n", encoding="utf-8")
    base = commit(root, "two modules")

    # Delete alpha's module declaration and its executable reference data.
    for path in (root / "Backend/games/alpha").iterdir():
        path.unlink()
    (root / "Backend/games/alpha").rmdir()
    reference.unlink()
    head = commit(root, "remove alpha")

    assert module_ids_for_diff(base, head, root) == ("alpha", "beta")
    assert app_resource_sources_for_diff(base, head, root) == (
        "Sources/Beta/table.json",
        "docs/reference/alpha/data.json",
    )

print("module_inventory_ok")
