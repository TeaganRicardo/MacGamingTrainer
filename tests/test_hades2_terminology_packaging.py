import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from games.hades2.terminology import TerminologyRegistry, _reference_path

SOURCE_REFERENCE = ROOT / "docs/reference/hades2/1.139672-24556151/ui_terminology.json"


def test_bundled_resource_wins_over_source_tree_fallback():
    with tempfile.TemporaryDirectory(prefix="mgt-terminology-bundle-") as temporary:
        resources = Path(temporary) / "Mac Gaming Trainer.app/Contents/Resources"
        module_file = resources / "Backend/games/hades2/terminology.py"
        source_reference = resources / "docs/reference/hades2/1.139672-24556151/ui_terminology.json"
        bundled_reference = resources / "ui_terminology.json"
        module_file.parent.mkdir(parents=True)
        source_reference.parent.mkdir(parents=True)
        shutil.copyfile(SOURCE_REFERENCE, source_reference)
        bundled_data = json.loads(SOURCE_REFERENCE.read_text(encoding="utf-8"))
        bundled_data["target"]["steamBuild"] = "bundled-resource"
        bundled_reference.write_text(json.dumps(bundled_data), encoding="utf-8")

        selected = _reference_path(module_file)
        assert selected == bundled_reference.resolve()
        assert TerminologyRegistry.load(selected).target["steamBuild"] == "bundled-resource"


def test_development_execution_falls_back_to_source_reference():
    with tempfile.TemporaryDirectory(prefix="mgt-terminology-source-") as temporary:
        repository = Path(temporary)
        module_file = repository / "Backend/games/hades2/terminology.py"
        source_reference = repository / "docs/reference/hades2/1.139672-24556151/ui_terminology.json"
        module_file.parent.mkdir(parents=True)
        source_reference.parent.mkdir(parents=True)
        shutil.copyfile(SOURCE_REFERENCE, source_reference)

        selected = _reference_path(module_file)
        assert selected == source_reference.resolve()
        assert TerminologyRegistry.load(selected).target["steamBuild"] == "24556151"


def test_present_but_invalid_bundle_is_not_hidden_by_source_fallback():
    with tempfile.TemporaryDirectory(prefix="mgt-terminology-invalid-bundle-") as temporary:
        resources = Path(temporary) / "Mac Gaming Trainer.app/Contents/Resources"
        module_file = resources / "Backend/games/hades2/terminology.py"
        bundled_reference = resources / "ui_terminology.json"
        source_reference = resources / "docs/reference/hades2/1.139672-24556151/ui_terminology.json"
        module_file.parent.mkdir(parents=True)
        source_reference.parent.mkdir(parents=True)
        shutil.copyfile(SOURCE_REFERENCE, source_reference)
        bundled_reference.write_text("{invalid", encoding="utf-8")

        assert _reference_path(module_file) == bundled_reference.resolve()
        try:
            TerminologyRegistry.load(_reference_path(module_file))
        except json.JSONDecodeError:
            pass
        else:
            raise AssertionError("invalid bundled terminology was silently replaced by source data")


def test_packaging_and_verification_include_only_the_hades_resource():
    build = (ROOT / "build.sh").read_text(encoding="utf-8")
    macos_workflow = (ROOT / ".github/workflows/build2-macos.yml").read_text(encoding="utf-8")
    module_matrix = (ROOT / ".github/workflows/module-build-matrix.yml").read_text(encoding="utf-8")
    manifest = json.loads((ROOT / "Backend/games/hades2/module.json").read_text(encoding="utf-8"))

    assert manifest["appResources"] == [
        {
            "source": "docs/reference/hades2/1.139672-24556151/ui_terminology.json",
            "destination": "ui_terminology.json",
        }
    ]
    assert "appResources" in build
    assert "ui_terminology.json" in macos_workflow
    assert "if [[ \"${{ matrix.game }}\" == \"hades2\" ]]" in module_matrix
    assert "if [[ \"${{ matrix.game }}\" == \"reference_fixture\" ]]" not in module_matrix
    assert "ui_terminology.json" in module_matrix


for _test in (
    test_bundled_resource_wins_over_source_tree_fallback,
    test_development_execution_falls_back_to_source_reference,
    test_present_but_invalid_bundle_is_not_hidden_by_source_fallback,
    test_packaging_and_verification_include_only_the_hades_resource,
):
    _test()

print("hades2_terminology_packaging_ok")
