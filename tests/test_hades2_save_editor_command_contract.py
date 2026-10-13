import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from games.hades2.command_contract import Hades2CommandContract, command_metadata


class Probe:
    def __init__(self):
        self.calls = []

    def open_save_editor(self, params):
        self.calls.append(("open", params))
        return {"profile": "Profile1", "relativePath": "Profile1.sav"}

    def save_editor_inventory(self, params):
        self.calls.append(("inventory", params))
        return {"sources": [], "targets": [], "defaultSource": None}

    def set_save_editor_target(self, params):
        self.calls.append(("target", params))
        return {"target": params["target"]}

    def validate_save_workspace(self, identifier):
        if identifier != "selected-document":
            raise ValueError("Save Editor document is no longer selected.")

    def query_save_editor(self, params):
        self.calls.append(("query", params))
        return {"domain": params["domain"], "items": []}

    def detail_save_editor(self, params):
        self.calls.append(("detail", params))
        return {"scene": "NemesisPostTrueEnding01", "sourceStatus": "available"}

    def stage_save_editor(self, params):
        self.calls.append(("stage", params))
        return {"count": 1, "changes": []}

    def review_save_editor(self):
        self.calls.append(("review", {}))
        return {"count": 1, "changes": []}

    def cancel_save_editor(self):
        self.calls.append(("cancel", {}))
        return {"count": 0, "changes": []}

    def apply_save_editor(self):
        self.calls.append(("apply", {}))
        return {"applied": True}


probe = Probe()
contract = Hades2CommandContract(probe)

opened = contract.dispatch("save_editor_open", {}, "open")
assert opened["profile"] == "Profile1"

queried = contract.dispatch(
    "save_editor_query",
    {
        "domain": "resources",
        "search": "moon",
        "offset": 20,
        "limit": 50,
        "path": [],
        "language": "en",
    },
    "query",
)
assert queried == {"domain": "resources", "items": []}

investigated = contract.dispatch(
    "save_editor_query",
    {"domain": "investigate", "search": "Nemesis", "stateFilter": "notRecorded", "language": "zh-CN"},
    "investigate",
)
assert investigated["domain"] == "investigate"
assert contract.dispatch(
    "save_editor_detail",
    {"entryId": "investigate:NemesisPostTrueEnding01", "language": "zh-CN"},
    "detail",
)["scene"] == "NemesisPostTrueEnding01"

staged = contract.dispatch(
    "save_editor_stage",
    {"entryId": "resource:MetaCurrency", "operation": "set", "value": 500},
    "stage",
)
assert staged["count"] == 1
assert contract.dispatch("save_editor_review", {}, "review")["count"] == 1
assert contract.dispatch("save_editor_cancel", {}, "cancel")["count"] == 0
assert contract.dispatch("save_editor_apply", {}, "apply")["applied"] is True

assert probe.calls == [
    ("open", {}),
    ("query", {
        "domain": "resources",
        "search": "moon",
        "offset": 20,
        "limit": 50,
        "path": [],
        "language": "en",
    }),
    ("query", {
        "domain": "investigate",
        "search": "Nemesis",
        "offset": 0,
        "limit": 100,
        "path": [],
        "language": "zh-CN",
        "stateFilter": "notRecorded",
    }),
    ("detail", {
        "entryId": "investigate:NemesisPostTrueEnding01",
        "language": "zh-CN",
    }),
    ("stage", {
        "entryId": "resource:MetaCurrency",
        "operation": "set",
        "value": 500,
    }),
    ("review", {}),
    ("cancel", {}),
    ("apply", {}),
]

metadata = {row["name"]: row["timeoutSeconds"] for row in command_metadata()}
for name in (
    "save_editor_inventory",
    "save_editor_open",
    "save_editor_target",
    "save_editor_query",
    "save_editor_detail",
    "save_editor_stage",
    "save_editor_review",
    "save_editor_cancel",
    "save_editor_apply",
):
    assert name in metadata
assert metadata["save_editor_apply"] == 30.0
assert metadata["save_editor_query"] == 30.0
assert metadata["save_editor_detail"] == 30.0

source = {"rootId": "backup-root", "relativePath": "Profile2_Temp.sav"}
target = {"rootId": "live-root", "relativePath": "Profile3.sav"}
selection = {"snapshotId": "verified-backup", "source": source, "target": target}
contract.dispatch("save_editor_inventory", {"snapshotId": "verified-backup"}, "inventory")
contract.dispatch("save_editor_open", selection, "explicit-open")
assert probe.calls[-2:] == [
    ("inventory", {"snapshotId": "verified-backup"}), ("open", selection),
]
assert contract.dispatch("save_editor_target", {
    "workspaceId": "selected-document", "target": target,
}, "target")["target"] == target
calls_before_invalid = list(probe.calls)
for command, params in (
    ("save_editor_open", {"snapshotId": ""}),
    ("save_editor_open", {"source": {"rootId": "main"}}),
    ("save_editor_open", {"source": {**source, "absolutePath": "/tmp/forged"}}),
    ("save_editor_target", {}),
    ("save_editor_target", {"target": target, "source": source}),
    ("save_editor_target", {"target": target, "workspaceId": "old-document"}),
    ("save_editor_apply", {"workspaceId": False}),
):
    try:
        contract.dispatch(command, params, "invalid-selection")
    except Exception:
        assert probe.calls == calls_before_invalid, (command, params)
    else:
        raise AssertionError(("invalid editor selection reached the adapter", command, params))

for command, params, presentation in (
    ("save_editor_query", {"domain": "resources", "limit": 0}, "hades2.saveEditor.error.invalidQuery"),
    ("save_editor_query", {"domain": "resources", "limit": 201}, "hades2.saveEditor.error.invalidQuery"),
    ("save_editor_query", {"domain": "resources", "search": "x" * 257}, "hades2.saveEditor.error.invalidQuery"),
    ("save_editor_query", {"domain": "resources", "language": "fr"}, "hades2.saveEditor.error.invalidQuery"),
    ("save_editor_query", {"domain": "investigate", "stateFilter": "forged"}, "hades2.saveEditor.error.invalidQuery"),
    ("save_editor_detail", {"entryId": "resource:MetaCurrency"}, "hades2.saveEditor.error.invalidQuery"),
    ("save_editor_stage", {"entryId": "", "operation": "set", "value": 1}, "hades2.saveEditor.error.invalidMutation"),
    ("save_editor_stage", {"entryId": "resource:MetaCurrency", "operation": "raw", "value": 1}, "hades2.saveEditor.error.invalidMutation"),
):
    try:
        contract.dispatch(command, params, "invalid")
    except Exception as error:
        assert getattr(error, "presentation", None) == presentation, (command, error)
    else:
        raise AssertionError("invalid Save Editor command was accepted: {}".format(command))

print("hades2_save_editor_command_contract_ok")
