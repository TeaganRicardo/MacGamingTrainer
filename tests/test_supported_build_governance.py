"""Canonical supported-build identity, generated native UUID, and drift rejection.

These are portable fixtures. No installed game, debugger, Save, or CI is used.
"""
import json
import plistlib
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Tools"))

from module_support import load_manifest, normalized_manifest
from supported_build import native_header, resolved_resource_source, validate_supported_build
from ci_docs_only import classify_scope

game_root = ROOT / "Backend/games"
for game in ("hades", "hades2"):
    path = game_root / game / "module.json"
    declaration = json.loads(path.read_text(encoding="utf-8"))
    supported = validate_supported_build(path)
    assert supported == declaration["supportedBuild"]
    symbol_data = json.loads((path.parent / "symbols.json").read_text(encoding="utf-8"))
    assert set(symbol_data).isdisjoint({"uuid", "steamBuildID", "architecture"})
    assert symbol_data["symbols"], game
    assert declaration["steamAppId"].isdigit()
    normalized = normalized_manifest(load_manifest(game))
    assert normalized["supportedBuild"] == supported

hades = json.loads((game_root / "hades/module.json").read_text(encoding="utf-8"))["supportedBuild"]
hades2 = json.loads((game_root / "hades2/module.json").read_text(encoding="utf-8"))["supportedBuild"]
assert "contentBuildInfo" in hades and "bundleVersion" not in hades
assert "bundleVersion" in hades2 and "contentBuildInfo" not in hades2

reference = ROOT / hades2["referenceDirectory"] / "ui_terminology.json"
terms = json.loads(reference.read_text(encoding="utf-8"))
assert terms["target"]["gameVersion"] == "1." + hades2["bundleVersion"]
assert terms["target"]["steamBuild"] == hades2["steamBuildID"]

hades_catalog = json.loads((game_root / "hades/catalog.json").read_text(encoding="utf-8"))
assert hades_catalog["steamBuildID"] == hades["steamBuildID"]

header = game_root / "hades2" / hades2["nativeUUIDHeader"]
assert header.read_text(encoding="utf-8") == native_header(
    hades2, game_name=json.loads((game_root / "hades2/module.json").read_text())["displayName"]
)
for source in ("EffectBlockQuery.c", "CommandMailbox.c"):
    c = (game_root / "hades2/native" / source).read_text(encoding="utf-8")
    assert '#include "SupportedBuildIdentity.h"' in c
    assert "MGT_SUPPORTED_GAME_UUID_BYTES" in c
    assert "0x35,0xcd,0x2e,0x50" not in c

preparation = (game_root / "hades2/preparation.py").read_text(encoding="utf-8")
for symbol in ("bundleVersion", "steamBuildID", "uuid", "originalExecutableSHA256"):
    assert "SUPPORTED_BUILD[" + repr(symbol) + "]" in preparation
assert hades2["originalExecutableSHA256"] not in preparation
assert hades2["uuid"] not in preparation
hades_transport = (game_root / "hades/transport.py").read_text(encoding="utf-8")
assert "self.supported_build['uuid']" in hades_transport

plist = plistlib.loads((ROOT / "Info.plist").read_bytes())
assert "supportedBuild" not in plist
assert "CFBundleShortVersionString" in plist and "CFBundleVersion" in plist
assert resolved_resource_source("@supportedBuild/ui_terminology.json", hades2) == (
    hades2["referenceDirectory"] + "/ui_terminology.json"
)
for invalid in ("@supportedBuild/../secrets", "@supportedBuild//etc/passwd", "@supportedBuild/"):
    try:
        resolved_resource_source(invalid, hades2)
    except ValueError:
        pass
    else:
        raise AssertionError("unsafe supported-build resource reference was accepted: " + invalid)
assert classify_scope(["Tools/supported_build.py"]) == {
    "docs_only": False, "needs_linux": True, "needs_macos": True, "needs_module": True,
}

with tempfile.TemporaryDirectory(prefix="mgt-supported-build-") as name:
    root = Path(name)
    module_dir = root / "Backend/games/example"
    reference_dir = root / "docs/reference/example/1.42-123"
    module_dir.mkdir(parents=True)
    reference_dir.mkdir(parents=True)
    build = {
        "architecture": "arm64", "bundleVersion": "42",
        "steamBuildID": "123",
        "uuid": "AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE",
        "originalExecutableSHA256": "a" * 64,
        "referenceDirectory": "docs/reference/example/1.42-123",
        "nativeUUIDHeader": "native/SupportedBuildIdentity.h",
    }
    module = module_dir / "module.json"
    symbols = module_dir / "symbols.json"
    generated = module_dir / "native/SupportedBuildIdentity.h"
    generated.parent.mkdir()
    terms_path = reference_dir / "ui_terminology.json"

    def write(build_value=None, symbol_data=None, terms_value=None, header_value=None):
        value = build if build_value is None else build_value
        module.write_text(json.dumps({"id": "example", "displayName": "Example", "supportedBuild": value}), encoding="utf-8")
        symbols.write_text(json.dumps({"symbols": {"lua_gettop": {"rva": 1}}} if symbol_data is None
                                      else symbol_data), encoding="utf-8")
        terms_path.write_text(json.dumps({"target": {"gameVersion": "1.42", "steamBuild": "123"}}
                                        if terms_value is None else terms_value), encoding="utf-8")
        generated.write_text(native_header(build, game_name="Example") if header_value is None else header_value, encoding="utf-8")

    def should_reject(**values):
        write(**values)
        try:
            validate_supported_build(module, root=root)
        except ValueError:
            pass
        else:
            raise AssertionError("supported-build drift was accepted: " + repr(values))

    write()
    assert validate_supported_build(module, root=root) == build
    should_reject(build_value={**build, "uuid": "BAD"})
    should_reject(build_value={**build, "bundleVersion": "43"})
    should_reject(build_value={**build, "contentBuildInfo": "38284"})
    should_reject(build_value={**build, "referenceDirectory": "../other"})
    should_reject(symbol_data={"uuid": build["uuid"], "symbols": {}})
    should_reject(terms_value={"target": {"gameVersion": "1.43", "steamBuild": "123"}})
    should_reject(terms_value={"target": {"gameVersion": "1.42", "steamBuild": "456"}})
    should_reject(header_value="#define MGT_SUPPORTED_GAME_UUID_BYTES 0x00\n")
    write()
    assert validate_supported_build(module, root=root) == build

print("supported_build_governance_ok")
