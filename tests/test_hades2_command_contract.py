import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from games.hades2.command_contract import Hades2CommandContract
from games.hades2.error_presentation import Hades2PresentationError


class ProbeAdapter:
    def __init__(self):
        self.calls = []

    def scan(self):
        self.calls.append(("scan",))
        return {"status": "not_running"}

    def execute(self, command, params):
        self.calls.append(("execute", command, dict(params)))
        return {"ok": True}


probe = ProbeAdapter()
contract = Hades2CommandContract(probe)

assert contract.dispatch("scan", {}, "scan-request") == {"status": "not_running"}
assert probe.calls == [("scan",)]

result = contract.dispatch(
    "acquire_chaos_pair",
    {"blessing": "ChaosHealthBlessing", "curse": "ChaosDamageCurse"},
    "chaos-request",
)
assert result == {"ok": True}
assert probe.calls[-1] == (
    "execute",
    "acquire_chaos_pair",
    {
        "blessing": "ChaosHealthBlessing",
        "curse": "ChaosDamageCurse",
        "requestId": "chaos-request",
    },
)

try:
    contract.dispatch("not_a_command", {}, "unknown-request")
except Hades2PresentationError as error:
    assert error.presentation == "hades2.error.invalidCommand"
    assert error.diagnostic == "未知命令。"
else:
    raise AssertionError("unknown Host command was accepted")

print("hades2_command_contract_basic_ok")
