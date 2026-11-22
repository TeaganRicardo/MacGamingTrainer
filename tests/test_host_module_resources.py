"""Portable behavior contract for per-module resource namespacing and string tables."""
import json
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Tools"))
sys.path.insert(0, str(ROOT / "tests"))

import product_support
from module_support import ManifestError
from swift_test_compiler import SWIFT_CORE_MODULE, SwiftModule, compile_swift_test, resolve_swiftc


def test_per_module_app_resource_namespacing() -> None:
    with tempfile.TemporaryDirectory(prefix="mgt-module-resources-ns-") as tmp:
        root = Path(tmp)
        for mod_id, dest in (("alpha", "Shared.json"), ("beta", "shared.json")):
            mod_dir = root / "Backend/games" / mod_id
            mod_dir.mkdir(parents=True)
            frontend_dir = root / "Sources" / mod_id.capitalize()
            frontend_dir.mkdir(parents=True)
            (frontend_dir / "Module.swift").write_text("// stub\n", encoding="utf-8")
            (root / "Sources" / mod_id).mkdir(parents=True, exist_ok=True)
            res = mod_dir / "resource.json"
            res.write_text("{}\n", encoding="utf-8")
            (mod_dir / "module.json").write_text(
                json.dumps(
                    {
                        "schemaVersion": 1,
                        "id": mod_id,
                        "displayName": mod_id.capitalize(),
                        "protocolVersion": 1,
                        "backend": {"adapter": f"games.{mod_id}.adapter:Adapter"},
                        "frontend": {
                            "sourceDirectory": f"Sources/{mod_id.capitalize()}",
                            "moduleType": f"{mod_id.capitalize()}Module",
                            "architectures": ["arm64"],
                            "minimumMacOS": "14.0",
                        },
                        "targetApplication": {
                            "processName": mod_id.capitalize(),
                            "bundleIdentifier": f"com.example.{mod_id}",
                        },
                        "appResources": [
                            {"source": f"Backend/games/{mod_id}/resource.json", "destination": dest}
                        ],
                    }
                ),
                encoding="utf-8",
            )
        (root / "app.json").write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "app": {"bundleIdentifier": "com.example.test", "displayName": "TestApp"},
                    "architectures": ["arm64"],
                    "minimumMacOS": "14.0",
                    "modules": ["alpha", "beta"],
                }
            ),
            encoding="utf-8",
        )
        (root / "Info.plist").write_bytes(plistlib.dumps({"CFBundleExecutable": "TestApp"}))
        shutil.copytree(ROOT / "Tools", root / "Tools")
        shutil.copytree(ROOT / "Backend/core", root / "Backend/core")
        result = subprocess.run(
            [sys.executable, str(root / "Tools/product_support.py"), "all"],
            cwd=root,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        normalized = json.loads(result.stdout)
        destinations = [item["destination"] for item in normalized["appResources"]]
        assert destinations == ["Modules/alpha/Shared.json", "Modules/beta/shared.json"], destinations

        # Intra-module case-insensitive collision must still fail.
        dup_manifest = root / "Backend/games/alpha/module.json"
        dup_data = json.loads(dup_manifest.read_text(encoding="utf-8"))
        dup_data["appResources"].append(
            {"source": "Backend/games/alpha/resource.json", "destination": "shared.json"}
        )
        dup_manifest.write_text(json.dumps(dup_data), encoding="utf-8")
        dup_result = subprocess.run(
            [sys.executable, str(root / "Tools/product_support.py"), "all"],
            cwd=root,
            capture_output=True,
            text=True,
        )
        assert dup_result.returncode != 0, dup_result.stdout + dup_result.stderr
        assert "appResources has duplicate destination" in dup_result.stderr, dup_result.stderr


def test_core_module_resources_and_string_table_swift() -> None:
    resources_swift = ROOT / "Sources/Core/Host/TrainerModuleResources.swift"
    assert resources_swift.is_file(), f"missing {resources_swift}"
    swiftc = resolve_swiftc()

    with tempfile.TemporaryDirectory(prefix="mgt-swift-module-res-") as tmp:
        work = Path(tmp)
        lang_stub = work / "LanguageStub.swift"
        lang_stub.write_text(
            'package enum TrainerPresentationLanguage: String, CaseIterable { case zhCN = "zh-CN", en }\n',
            encoding="utf-8",
        )
        main = work / "main.swift"
        main.write_text(
            """
import Foundation

let tempRoot = URL(fileURLWithPath: CommandLine.arguments[1])
precondition(TrainerModuleResources.url(moduleID: "../escape", relativePath: "a.json", extraRoots: [tempRoot]) == nil)
precondition(TrainerModuleResources.url(moduleID: "alpha", relativePath: "../b.json", extraRoots: [tempRoot]) == nil)
precondition(TrainerModuleResources.url(moduleID: "alpha", relativePath: "flat_only.json", extraRoots: [tempRoot]) == nil)
precondition(TrainerModuleResources.url(moduleID: "beta", relativePath: "alpha.en.json", extraRoots: [tempRoot]) == nil)

let loaded = TrainerModuleStringTable(
    moduleID: "alpha",
    extraRoots: [tempRoot],
    resolveArgumentKeys: true,
    transform: { text, language in
        text.replacingOccurrences(of: "{term:greeting}", with: language == .en ? "Hello" : "你好")
    }
)
precondition(loaded.hasKey("alpha.title"))
precondition(!loaded.hasKey("alpha.onlyEn"))
precondition(loaded.string("alpha.banner", language: .en, arguments: ["alpha.title", "Ignored"]) == "Hello - Title []")
precondition(loaded.string("alpha.banner", language: .zhCN, arguments: ["World"]) == "你好 - World []")
""",
            encoding="utf-8",
        )
        mod_dir = work / "res/Modules/alpha"
        mod_dir.mkdir(parents=True)
        (work / "res/flat_only.json").write_text('{"entries":{}}', encoding="utf-8")
        (mod_dir / "alpha.en.json").write_text(
            json.dumps(
                {
                    "entries": {
                        "alpha.title": "Title",
                        "alpha.onlyEn": "EN",
                        "alpha.banner": "{term:greeting} - {0} [{2}]",
                    }
                }
            ),
            encoding="utf-8",
        )
        (mod_dir / "alpha.zh-CN.json").write_text(
            json.dumps(
                {
                    "entries": {
                        "alpha.title": "标题",
                        "alpha.banner": "{term:greeting} - {0} [{2}]",
                    }
                }
            ),
            encoding="utf-8",
        )
        binary = work / "module-res-test"
        compile_swift_test(
            modules=[SwiftModule(SWIFT_CORE_MODULE, [lang_stub, resources_swift])],
            harness_sources=[main],
            output=binary,
            flags=(),
            swiftc=swiftc,
            cwd=ROOT,
        )
        subprocess.run([str(binary), str(work / "res")], check=True)


if __name__ == "__main__":
    test_per_module_app_resource_namespacing()
    test_core_module_resources_and_string_table_swift()
    print("host_module_resources_ok")
