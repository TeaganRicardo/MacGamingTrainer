import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))
sys.path.insert(0, str(ROOT / "Tools"))

from games.hades2.terminology import TerminologyRegistry, _reference_path
from supported_build import resolved_resource_source

MANIFEST = json.loads((ROOT / "Backend/games/hades2/module.json").read_text(encoding="utf-8"))
SUPPORTED_BUILD = MANIFEST["supportedBuild"]
SOURCE_REFERENCE = ROOT / SUPPORTED_BUILD["referenceDirectory"] / "ui_terminology.json"


def test_bundled_resource_wins_over_source_tree_fallback():
    with tempfile.TemporaryDirectory(prefix="mgt-terminology-bundle-") as temporary:
        resources = Path(temporary) / "Mac Gaming Trainer.app/Contents/Resources"
        module_file = resources / "Backend/games/hades2/terminology.py"
        source_reference = resources / SUPPORTED_BUILD["referenceDirectory"] / "ui_terminology.json"
        bundled_reference = resources / "Modules/hades2/ui_terminology.json"
        module_file.parent.mkdir(parents=True)
        source_reference.parent.mkdir(parents=True)
        bundled_reference.parent.mkdir(parents=True)
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
        source_reference = repository / SUPPORTED_BUILD["referenceDirectory"] / "ui_terminology.json"
        module_file.parent.mkdir(parents=True)
        source_reference.parent.mkdir(parents=True)
        shutil.copyfile(SOURCE_REFERENCE, source_reference)

        selected = _reference_path(module_file)
        assert selected == source_reference.resolve()
        assert TerminologyRegistry.load(selected).target["steamBuild"] == SUPPORTED_BUILD["steamBuildID"]


def test_present_but_invalid_bundle_is_not_hidden_by_source_fallback():
    with tempfile.TemporaryDirectory(prefix="mgt-terminology-invalid-bundle-") as temporary:
        resources = Path(temporary) / "Mac Gaming Trainer.app/Contents/Resources"
        module_file = resources / "Backend/games/hades2/terminology.py"
        bundled_reference = resources / "Modules/hades2/ui_terminology.json"
        source_reference = resources / SUPPORTED_BUILD["referenceDirectory"] / "ui_terminology.json"
        module_file.parent.mkdir(parents=True)
        source_reference.parent.mkdir(parents=True)
        bundled_reference.parent.mkdir(parents=True)
        shutil.copyfile(SOURCE_REFERENCE, source_reference)
        bundled_reference.write_text("{invalid", encoding="utf-8")

        assert _reference_path(module_file) == bundled_reference.resolve()
        try:
            TerminologyRegistry.load(_reference_path(module_file))
        except json.JSONDecodeError:
            pass
        else:
            raise AssertionError("invalid bundled terminology was silently replaced by source data")


def test_product_contains_hades_resources_and_isolated_modules_exclude_them():
    build = (ROOT / "build.sh").read_text(encoding="utf-8")
    manifest = MANIFEST

    assert manifest["appResources"] == [
        {
            "source": "@supportedBuild/ui_terminology.json",
            "destination": "ui_terminology.json",
        },
        {
            "source": "@supportedBuild/installed_source_hashes.json",
            "destination": "hades2.installed_source_hashes.json",
        },
        {
            "source": "Sources/Hades2/Presentation/Localization/hades2.zh-CN.json",
            "destination": "hades2.zh-CN.json",
        },
        {
            "source": "Sources/Hades2/Presentation/Localization/hades2.en.json",
            "destination": "hades2.en.json",
        },
    ]
    assert resolved_resource_source(
        manifest["appResources"][0]["source"], SUPPORTED_BUILD
    ) == SOURCE_REFERENCE.relative_to(ROOT).as_posix()
    assert "package-app-resources" in build

    # Both shipped languages must exist in the source tree: a missing table
    # would silently drop one language back to raw keys at runtime.
    for language in ("zh-CN", "en"):
        table = ROOT / f"Sources/Hades2/Presentation/Localization/hades2.{language}.json"
        assert table.is_file(), f"missing packaged Hades presentation table: {table}"

    # Verify Tools/package_app.py and Tools/verify_module_build.py own declared
    # resource packaging, presence and non-selected exclusion generically.
    import module_support
    import package_app
    import plistlib
    import product_support
    import verify_module_build

    with tempfile.TemporaryDirectory(prefix="mgt-hades2-pkg-") as temporary:
        project = Path(temporary)
        for rel in ("Backend", "Sources", "Resources", "Tools", "docs/reference/hades", SUPPORTED_BUILD["referenceDirectory"]):
            shutil.copytree(ROOT / rel, project / rel, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        for rel in ("Info.plist", "app.json"):
            shutil.copy2(ROOT / rel, project / rel)

        orig_roots = (module_support.ROOT, product_support.ROOT, verify_module_build.ROOT)
        try:
            module_support.ROOT = project
            product_support.ROOT = project
            verify_module_build.ROOT = project
            hades_selection = product_support.load_selection("hades")
            hades_mod = hades_selection.modules[0]
            dist = project / "dist"
            app_path = dist / f"{hades_mod.app.display_name}.app"
            res_dir = app_path / "Contents/Resources"
            (res_dir / "Backend/games/hades").mkdir(parents=True)
            shutil.copy2(project / "Backend/games/hades/module.json", res_dir / "Backend/games/hades/module.json")
            (res_dir / "ACTIVE_GAME_ID").write_text("hades\n", encoding="utf-8")
            norm_manifest = project / "hades.normalized.json"
            norm_manifest.write_text(json.dumps(hades_selection.normalized()), encoding="utf-8")
            package_app.package_app_resources(norm_manifest, project, res_dir)
            if hades_mod.requirements.lldb_python:
                shutil.copytree(project / "Backend/debugger", res_dir / "Backend/debugger")
            for lib in hades_mod.native_libraries:
                native = res_dir / "Backend/games/hades/native" / lib.filename
                native.parent.mkdir(parents=True, exist_ok=True)
                native.write_bytes(b"stub")
            exe = app_path / "Contents/MacOS" / hades_mod.app.executable
            exe.parent.mkdir(parents=True)
            exe.write_bytes(b"stub")
            (app_path / "Contents/Info.plist").write_bytes(plistlib.dumps({
                "CFBundleIdentifier": hades_mod.app.bundle_identifier,
                "CFBundleName": hades_mod.app.display_name,
                "CFBundleDisplayName": hades_mod.app.display_name,
                "CFBundleExecutable": hades_mod.app.executable,
            }))
            runtime_src = json.loads((project / "Tools/python_runtime.json").read_text(encoding="utf-8"))
            py_root = res_dir / "Python"
            py_root.mkdir(parents=True)
            arches = list(hades_selection.architectures)
            (py_root / "runtime.json").write_text(json.dumps({
                "schemaVersion": runtime_src["schemaVersion"],
                "provider": runtime_src["provider"],
                "release": runtime_src["release"],
                "version": runtime_src["version"],
                "architectures": arches,
                "distributions": {a: runtime_src["distributions"][a] for a in arches},
            }), encoding="utf-8")
            for a in arches:
                p = py_root / a / "bin/python3"
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
                p.chmod(0o755)

            assert verify_module_build.verify_module_build("hades", dist) == app_path.resolve()

            leaked = res_dir / "Modules/hades2/ui_terminology.json"
            leaked.parent.mkdir(parents=True, exist_ok=True)
            leaked.write_text("{}", encoding="utf-8")
            try:
                verify_module_build.verify_module_build("hades", dist)
            except ValueError as err:
                assert "hades2" in str(err) or "selection" in str(err), err
            else:
                raise AssertionError("isolated build allowed foreign hades2 resource directory")
            shutil.rmtree(leaked.parent)

            flat_leak = res_dir / "ui_terminology.json"
            flat_leak.write_text("{}", encoding="utf-8")
            try:
                verify_module_build.verify_module_build("hades", dist)
            except ValueError as err:
                assert "hades2" in str(err) or "ui_terminology.json" in str(err), err
            else:
                raise AssertionError("isolated build allowed legacy flat ui_terminology.json")
        finally:
            module_support.ROOT, product_support.ROOT, verify_module_build.ROOT = orig_roots


for _test in (
    test_bundled_resource_wins_over_source_tree_fallback,
    test_development_execution_falls_back_to_source_reference,
    test_present_but_invalid_bundle_is_not_hidden_by_source_fallback,
    test_product_contains_hades_resources_and_isolated_modules_exclude_them,
):
    _test()

print("hades2_terminology_packaging_ok")
