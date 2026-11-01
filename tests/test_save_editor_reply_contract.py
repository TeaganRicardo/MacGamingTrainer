"""Core owns workspace reply identity; both game models retain their own editing semantics."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
core = (ROOT / "Sources/Core/Save/TrainerSaveEditorReplyCoordinator.swift").read_text(encoding="utf-8")
hades = (ROOT / "Sources/Hades/HadesSaveEditorModel.swift").read_text(encoding="utf-8")
hades2 = (ROOT / "Sources/Hades2/Hades2SaveEditorModel.swift").read_text(encoding="utf-8")
native = (ROOT / "tests/test_multi_game_contexts.py").read_text(encoding="utf-8")

for method in (
    "func beginNewDocumentRead() -> Ticket",
    "func capture(_ lane: Lane? = nil, bindsDocument: Bool = true) -> Ticket",
    "func accepts(_ ticket: Ticket) -> Bool",
    "func invalidate(_ lane: Lane)",
    "func owns(workspaceID: String?, baselineGeneration: String?) -> Bool",
    "func bind(workspaceID: String, baselineGeneration: String)",
    "func retire()",
):
    assert method in core, method

for name, source in (("Hades I", hades), ("Hades II", hades2)):
    assert "private let requests = TrainerSaveEditorReplyCoordinator()" in source, name
    assert "requests.beginNewDocumentRead()" in source, name
    assert "requests.capture(" in source, name
    assert "requests.accepts(ticket)" in source, name
    assert "requests.owns(workspaceID:" in source, name
    assert "requests.bind(workspaceID:" in source, name
    assert "requests.retire()" in source, name
    assert "queryGeneration" not in source and "detailGeneration" not in source, name
    assert ".query" in source and ".detail" in source, name

# Both adapters still own game-specific editing/draft presentation.
assert "activeEdits" in hades and "failedDrafts" in hades
assert "typedDrafts" in hades2 and "membershipDrafts" in hades2
assert "Hades" not in core and "Hades2" not in core
assert "save_editor_close" in hades and ".saveEditorClose" in hades2
assert "self.release(abandoned)" in hades
assert "self.releaseWorkspace(abandoned)" in hades2
assert "self.session.lifecycleID == lifecycle" in hades
assert "lane: .advancedDetail" in hades2
assert "lane: .review" in hades2
assert "lane: .query" in hades2 and "lane: .query" in hades
assert "requests.invalidate(.query)" in hades and "requests.invalidate(.query)" in hades2

# The macOS Core smoke uses two independent game-shaped instances and drives
# overlapping query, rapid source reads, target switch, stale row/Apply, and
# close/reopen (including reused backend identity) against actual Swift logic.
for phrase in (
    'verifySaveEditorReplies("Hades I")',
    'verifySaveEditorReplies("Hades II")',
    "rapid source reads accepted an obsolete result",
    "overlapping search overwrote latest result or focused draft",
    "target switch adopted an old response",
    "stale row/Apply crossed an installed document baseline",
    "close/reopen accepted a reply from the retired tool window",
):
    assert phrase in native, phrase

print("save_editor_reply_coordination_contract_ok")
