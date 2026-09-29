"""Resident-runtime declarations are validated by normal module validation (#213)."""
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Tools"))

from resident_runtime import (
    ResidentRuntimeDeclarationError,
    parse_resident_runtime_declaration,
)

MODULE_SUPPORT = (ROOT / "Tools/module_support.py").read_text(encoding="utf-8")
REVISION_GATE = (ROOT / "Tools/check_runtime_revision.py").read_text(encoding="utf-8")


def expect_error(declaration, manifest, exists=lambda _path: True, fragment="residentRuntime"):
    try:
        parse_resident_runtime_declaration(
            declaration,
            manifest_path=manifest,
            source_exists=exists,
        )
    except ResidentRuntimeDeclarationError as error:
        assert fragment in str(error), (fragment, str(error))
        return
    raise AssertionError(f"expected declaration failure: {declaration!r}")


with tempfile.TemporaryDirectory(prefix="mgt-resident-runtime-") as tmp:
    root = Path(tmp)
    manifest = root / "Backend/games/alpha/module.json"
    runtime = manifest.parent / "runtime/resident.lua"
    runtime.parent.mkdir(parents=True)
    runtime.write_text("local M = { version = 1, revision = 1 }\n", encoding="utf-8")
    manifest.write_text("{}\n", encoding="utf-8")

    valid = {
        "source": "runtime/resident.lua",
        "previousRevisionPattern": r"previousModule\.revision\s*~=\s*(\d+)",
        "moduleRevisionPattern": r"version\s*=\s*1\s*,\s*revision\s*=\s*(\d+)",
    }
    spec = parse_resident_runtime_declaration(
        valid,
        manifest_path=manifest,
        source_exists=lambda path: Path(path).is_file(),
    )
    assert spec.source == "runtime/resident.lua"
    assert spec.runtime_path == manifest.parent / "runtime/resident.lua"
    assert spec.previous_revision_pattern.search("previousModule.revision ~= 7")
    assert spec.module_revision_pattern.search("version = 1, revision = 7")

    expect_error(None, manifest, fragment="must be an object")
    expect_error({}, manifest, fragment=".source")
    expect_error({"source": ""}, manifest, fragment=".source")
    expect_error({"source": " runtime/resident.lua"}, manifest, fragment="whitespace")
    expect_error({"source": "runtime/resident.lua "}, manifest, fragment="whitespace")
    expect_error({"source": "/tmp/resident.lua"}, manifest, fragment="inside the module directory")
    expect_error({"source": "../resident.lua"}, manifest, fragment="inside the module directory")
    expect_error({"source": "runtime/missing.lua"}, manifest, exists=lambda _path: False, fragment="does not name a file")
    expect_error(
        {"source": "runtime/resident.lua", "previousRevisionPattern": "("},
        manifest,
        fragment="previousRevisionPattern",
    )
    expect_error(
        {"source": "runtime/resident.lua", "moduleRevisionPattern": ""},
        manifest,
        fragment="moduleRevisionPattern",
    )

# The build/module validator and the diff gate must consume the same parser.
assert "parse_resident_runtime_declaration" in MODULE_SUPPORT
assert "parse_resident_runtime_declaration" in REVISION_GATE

# The revision gate must not retain a second copy of declaration validation.
for duplicated in (
    "residentRuntime.source must be a non-empty string",
    "previousRevisionPattern must be a non-empty string",
    "moduleRevisionPattern must be a non-empty string",
):
    assert duplicated not in REVISION_GATE, f"duplicate residentRuntime validation survived: {duplicated}"

print("resident_runtime_manifest_validation_ok")
