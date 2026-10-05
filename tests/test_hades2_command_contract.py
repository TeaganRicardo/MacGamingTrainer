import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from games.hades2.command_contract import Hades2CommandContract


class ProbeAdapter:
    def __init__(self):
        self.calls = []

    def scan(self):
        self.calls.append(("scan",))
        return {"status": "not_running"}


probe = ProbeAdapter()
contract = Hades2CommandContract(probe)

assert contract.dispatch("scan", {}, "scan-request") == {"status": "not_running"}
assert probe.calls == [("scan",)]

try:
    contract.dispatch("not_a_command", {}, "unknown-request")
except ValueError as error:
    assert str(error) == "未知命令。"
else:
    raise AssertionError("unknown Host command was accepted")

print("hades2_command_contract_basic_ok")
