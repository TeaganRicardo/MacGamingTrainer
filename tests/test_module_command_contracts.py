"""Behavior contracts for module command contracts, inner/outer budgets, and typed requests."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Tools"))
sys.path.insert(0, str(ROOT / "Backend"))

from swift_test_compiler import SWIFT_CORE_MODULE, SwiftModule, compile_swift_test, resolve_swiftc  # noqa: E402


def test_manifests_declare_command_contract_and_generate_parity() -> None:
    generator = ROOT / "Tools/generate_module_commands.py"
    assert generator.is_file(), f"missing generic generator {generator}"
    assert not (ROOT / "Tools/games/hades2/generate_hades2_command_binding.py").exists()

    for game_id, swift_dir, enum_name in (
        ("hades", "Sources/Hades", "HadesCommand"),
        ("hades2", "Sources/Hades2", "Hades2Command"),
    ):
        manifest = json.loads((ROOT / "Backend/games" / game_id / "module.json").read_text(encoding="utf-8"))
        assert "commandContract" in manifest, f"{game_id}/module.json missing commandContract"
        checked_in = ROOT / swift_dir / "Generated" / f"{enum_name}.generated.swift"
        assert checked_in.is_file(), f"missing checked-in generated file {checked_in}"
        with tempfile.TemporaryDirectory(prefix=f"mgt-cmd-{game_id}-") as tmp:
            out = Path(tmp) / f"{enum_name}.generated.swift"
            subprocess.run(
                [sys.executable, str(generator), game_id, str(out)],
                cwd=ROOT,
                check=True,
            )
            assert out.read_bytes() == checked_in.read_bytes(), f"{game_id} generated command contract drifted"


def test_generated_flags_match_both_swift_apis() -> None:
    swiftc = resolve_swiftc()
    with tempfile.TemporaryDirectory(prefix="mgt-cmd-swift-") as tmp:
        work = Path(tmp)
        stub = work / "Stub.swift"
        stub.write_text(
            """
import Foundation

package struct GameModuleDescriptor: Identifiable, Hashable, Sendable {
    package let id: String
    package let displayName: String
    package let targetProcessName: String
    package let targetBundleIdentifier: String
    let targetExecutablePathSuffix: String
    package let expectedHostProtocolVersion: Int
    package let expectedModuleProtocolVersion: Int
    let supportsSaveManagement: Bool
    package init(id: String, displayName: String, targetProcessName: String, targetBundleIdentifier: String,
                 targetExecutablePathSuffix: String = "", expectedHostProtocolVersion: Int,
                 expectedModuleProtocolVersion: Int, supportsSaveManagement: Bool) {
        self.id = id; self.displayName = displayName
        self.targetProcessName = targetProcessName; self.targetBundleIdentifier = targetBundleIdentifier
        self.targetExecutablePathSuffix = targetExecutablePathSuffix
        self.expectedHostProtocolVersion = expectedHostProtocolVersion
        self.expectedModuleProtocolVersion = expectedModuleProtocolVersion
        self.supportsSaveManagement = supportsSaveManagement
    }
}
""",
            encoding="utf-8",
        )
        main = work / "main.swift"
        main.write_text(
            """
import Foundation

precondition(Hades2Command.setDesired.offlineIntent(connected: false))
precondition(!Hades2Command.setDesired.offlineIntent(connected: true))
precondition(!Hades2Command.setDesired.requiresTrustedTarget(connected: false))
precondition(Hades2Command.setDesired.requiresTrustedTarget(connected: true))
precondition(!Hades2Command.scan.requiresTrustedTarget(connected: true))
precondition(!Hades2Command.saveEditorApply.requiresTrustedTarget(connected: true))
precondition(Hades2Command.spawnReward.requiresTrustedTarget(connected: false))

precondition(HadesCommand.setFeature.offlineIntent(connected: false))
precondition(!HadesCommand.setFeature.offlineIntent(connected: true))
precondition(!HadesCommand.setFeature.requiresTrustedTarget(connected: false))
precondition(HadesCommand.setFeature.requiresTrustedTarget(connected: true))
precondition(!HadesCommand.catalog.requiresTrustedTarget(connected: true))
precondition(!HadesCommand.saveEditorOpen.requiresTrustedTarget(connected: true))
precondition(HadesCommand.addTrait.requiresTrustedTarget(connected: false))
precondition(HadesCommand.connect.timeout == 190.0)
precondition(HadesCommand.launch.timeout > 32.0)

let rarityReq = Hades2Request.setBoonRarity(target: "Epic", forceLegendary: true, forceDuo: false)
precondition(rarityReq.params["multiplier"] == nil)
""",
            encoding="utf-8",
        )
        binary = work / "cmd-contract-check"
        compile_swift_test(
            modules=[
                SwiftModule(
                    SWIFT_CORE_MODULE,
                    [
                        ROOT / "Sources/Core/Runtime/TrainerJSON.swift",
                        ROOT / "Sources/Core/Runtime/BackendProcess.swift",
                        ROOT / "Sources/Core/Runtime/BackendClient.swift",
                        ROOT / "Sources/Core/Runtime/TrainerBackendSession.swift",
                        stub,
                    ],
                ),
                SwiftModule(
                    "Hades2",
                    [
                        ROOT / "Sources/Hades2/Hades2API.swift",
                        ROOT / "Sources/Hades2/Hades2Types.swift",
                        ROOT / "Sources/Hades2/Generated/Hades2Command.generated.swift",
                        ROOT / "Sources/Hades2/Generated/Hades2Feature.generated.swift",
                    ],
                    (SWIFT_CORE_MODULE,),
                ),
                SwiftModule(
                    "Hades",
                    [
                        ROOT / "Sources/Hades/HadesAPI.swift",
                        ROOT / "Sources/Hades/Generated/HadesCommand.generated.swift",
                    ],
                    (SWIFT_CORE_MODULE,),
                ),
            ],
            harness_sources=[main],
            output=binary,
            flags=(),
            swiftc=swiftc,
            cwd=ROOT,
        )
        subprocess.run([str(binary)], check=True)


def test_small_timeout_values_preserved() -> None:
    import generate_module_commands as generator
    spec = SimpleNamespace(metadata='fixture:commands', enum_name='FixtureCommand', default_timeout_seconds=1e-10)
    rows = [{'name': 'quick', 'timeoutSeconds': 0.04, 'requiresTrustedTarget': True, 'supportsOfflineIntent': False},
            {'name': 'precise', 'timeoutSeconds': 2e-10, 'requiresTrustedTarget': True, 'supportsOfflineIntent': False}]
    with patch.object(generator, 'load_manifest', return_value=SimpleNamespace(command_contract=spec)), \
            patch.object(generator, 'load_command_rows', return_value=rows):
        text = generator.render_commands('fixture')
    import re
    for label, expected in (('case .quick', 0.04), ('case .precise', 2e-10), ('default', 1e-10)):
        value = re.search(re.escape(label) + r': return ([0-9.e+-]+)', text)
        assert value is not None and float(value.group(1)) == expected, text


def test_every_command_outer_timeout_exceeds_worst_case_inner_budget() -> None:
    from games.hades.command_contract import command_budget_audit as hades_audit
    from games.hades2.command_contract import command_budget_audit as hades2_audit

    for game_id, rows in (("hades", hades_audit()), ("hades2", hades2_audit())):
        assert rows, game_id
        for row in rows:
            outer = float(row["timeoutSeconds"])
            inner = float(row["worstCaseInnerSeconds"])
            assert outer > inner, f"{game_id}.{row['name']}: outer {outer}s <= worst-case inner {inner}s"


def test_hades2_retired_boon_rarity_multiplier_rejected_on_wire() -> None:
    from games.hades2.command_contract import Hades2CommandContract

    class _Probe:
        def set_boon_rarity_desired(self, config):
            return config

    contract = Hades2CommandContract(_Probe())
    accepted = contract.dispatch(
        "set_boon_rarity_desired",
        {"target": "Epic", "forceLegendary": True, "forceDuo": False},
        "r1",
    )
    assert accepted == {"target": "Epic", "forceLegendary": True, "forceDuo": False}
    try:
        contract.dispatch(
            "set_boon_rarity_desired",
            {"target": "Epic", "multiplier": 100, "forceLegendary": True, "forceDuo": False},
            "r2",
        )
    except Exception:
        pass
    else:
        raise AssertionError("set_boon_rarity_desired accepted retired multiplier field")


if __name__ == "__main__":
    test_manifests_declare_command_contract_and_generate_parity()
    test_small_timeout_values_preserved()
    test_generated_flags_match_both_swift_apis()
    test_every_command_outer_timeout_exceeds_worst_case_inner_budget()
    test_hades2_retired_boon_rarity_multiplier_rejected_on_wire()
    print("module_command_contracts_ok")
