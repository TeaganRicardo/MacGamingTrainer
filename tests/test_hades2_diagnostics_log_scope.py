"""Verify Hades II diagnostics returns only key+arguments checks and state, with no Host log ZIP builder."""
import json
import re
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from games.hades2 import command_contract, diagnostics
from hades2_resident_session_fakes import hades2_adapter_context


class DeadRuntime:
    def alive(self):
        return False


class FakeAdapter:
    game_id = "hades2"
    module_protocol_version = 5
    runtime = DeadRuntime()
    state = {}

    def __init__(self, context):
        self.context = context

    def list_profiles(self):
        raise AssertionError("diagnostic export must not enumerate private user Profiles")


diagnostics_source = (ROOT / "Backend/games/hades2/diagnostics.py").read_text(encoding="utf-8")
assert not hasattr(diagnostics, "export_diagnostics"), "Python export_diagnostics ZIP builder must be removed"
assert "export_diagnostics" not in command_contract.COMMAND_SPECS
for forbidden in ("zipfile", "current-session.json", "trainer-host.log", "log_dir"):
    assert forbidden not in diagnostics_source, f"Hades II diagnostics must not inspect Host logs: {forbidden}"

with tempfile.TemporaryDirectory(prefix="mgt-hades2-diagnostics-contract-") as td:
    home = Path(td) / "home"
    adapter = FakeAdapter(hades2_adapter_context(home))
    en_entries = json.loads(
        (ROOT / "Sources/Hades2/Presentation/Localization/hades2.en.json").read_text(encoding="utf-8")
    )["entries"]
    zh_entries = json.loads(
        (ROOT / "Sources/Hades2/Presentation/Localization/hades2.zh-CN.json").read_text(encoding="utf-8")
    )["entries"]

    with (
        patch.object(diagnostics.preparation, "GAME", home / "MissingGame"),
        patch.object(diagnostics.preparation, "SAVES", home / "MissingSaves"),
        patch.object(diagnostics.preparation, "compatibility", side_effect=RuntimeError("no game")),
        patch("core.target_probe.subprocess.run", return_value=SimpleNamespace(returncode=1, stdout="", stderr="missing")),
    ):
        report = diagnostics.build_diagnostics(adapter)

    assert "diagnosticBundle" not in report
    assert "checks" in report and "state" in report
    assert "profiles" not in report
    for check in report["checks"]:
        name = check["name"]
        assert name.startswith("hades2.diagnostics.check."), name
        assert name in en_entries and name in zh_entries, name
        assert not re.search(r"[\u3400-\u9fff]", name), name
        detail = check["detail"]
        if detail.startswith("hades2.diagnostics.detail."):
            assert detail in en_entries and detail in zh_entries, detail
        for arg in check.get("nameArguments", []):
            if str(arg).startswith("hades2."):
                assert arg in en_entries and arg in zh_entries, arg

print("hades2_diagnostics_log_scope_ok")
