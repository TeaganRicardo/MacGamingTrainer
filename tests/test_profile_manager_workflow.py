"""Profile selection follows acknowledged inventories without losing name drafts."""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "Sources/Core/UI/Components/TrainerProfileSelection.swift"
swiftc = shutil.which("swiftc")
if not swiftc:
    raise SystemExit("swiftc required")

with tempfile.TemporaryDirectory(prefix="mgt-profile-selection-") as directory:
    folder = Path(directory)
    main = folder / "main.swift"
    main.write_text(r'''
var state = TrainerProfileSelection()
state.reconcile([], busy: false)
precondition(state.selectedName.isEmpty)
state.draftName = " \n "
precondition(state.beginSave() == nil)
state.reconcile(["First", "Second"], busy: false)
precondition(state.selectedName == "First")
state.selectedName = "Second"
state.draftName = " New profile "
precondition(state.beginSave() == "New profile")
state.reconcile(["First", "Second"], busy: true)
precondition(state.selectedName == "Second", "unacknowledged name became selectable")
state.reconcile(["First", "New profile", "Second"], busy: false)
precondition(state.selectedName == "New profile", "successful creation did not select its stored row")
precondition(state.draftName == " New profile ", "refresh replaced the user's draft")

state.draftName = "Rejected"
precondition(state.beginSave() == "Rejected")
state.reconcile(["First", "New profile", "Second"], busy: false)
precondition(state.selectedName == "New profile" && state.pendingSavedName == nil)
state.selectedName = "Second"
state.reconcile(["First", "New profile", "Rejected", "Second"], busy: false)
precondition(state.selectedName == "Second", "failed save redirected a later external refresh")
precondition(state.draftName == "Rejected", "failed save discarded the editable name")

state.reconcile(["First"], busy: false)
precondition(state.selectedName == "First", "deleted selection did not reconcile")
state.reconcile([], busy: false)
precondition(state.selectedName.isEmpty, "empty inventory retained a load/delete target")
state.reconcile(["Restored"], busy: false)
precondition(state.selectedName == "Restored")
precondition(TrainerProfileEntry(name: "Restored", updatedAt: "").title == "Restored")
precondition(TrainerProfileEntry(name: "Restored", updatedAt: "Today").title == "Restored · Today")
print("profile_selection_workflow_ok")
''', encoding="utf-8")
    binary = folder / "selection"
    subprocess.run([swiftc, str(SOURCE), str(main), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)

# Both modules bind the same workflow. Contents, transport and shortcut
# compatibility remain at the game boundary; Core never decodes a profile.
for path, start, end in (
    ("Sources/Hades/HadesManagement.swift", "struct HadesProfileManagerView", "struct HadesDiagnosticsView"),
    ("Sources/Hades2/Views/Hades2ManagementViews.swift", "struct Hades2ProfileManagerView", "struct Hades2DiagnosticsView"),
):
    source = (ROOT / path).read_text()
    adapter = source[source.index(start):source.index(end)]
    assert "TrainerProfileManagerView(" in adapter
    assert "Picker(" not in adapter and "TrainerSheetScaffold(" not in adapter
    for command in ("model.listProfiles", "model.saveProfile", "model.loadProfile", "model.deleteProfile"):
        assert command in adapter
    assert "ManagementError(model, localization: localization)" in adapter

hades2 = (ROOT / "Sources/Hades2/Views/Hades2ManagementViews.swift").read_text()
assert "model.profileShortcutWarning.map" in hades2
assert ".onDisappear { model.clearProfileShortcutWarning() }" in hades2
print("profile_manager_module_adapters_ok")
