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
state.reconcile([])
precondition(state.selectedName.isEmpty)
state.draftName = " \n "
precondition(state.beginSave() == nil)
state.reconcile(["First", "Second"])
precondition(state.selectedName == "First")
state.selectedName = "Second"
state.draftName = " New profile "
let created = state.beginSave()!
precondition(created.name == "New profile" && state.beginSave() == nil)
state.reconcile(["First", "New profile", "Second"])
precondition(state.selectedName == "Second", "inventory update alone selected an unacknowledged save")
state.completeSave(created, succeeded: true)
state.reconcile(["First", "New profile", "Second"])
precondition(state.selectedName == "New profile", "successful creation did not select its stored row")
precondition(state.draftName == " New profile ", "refresh replaced the user's draft")

// Completion and inventory publications may arrive in either order.
state.draftName = "Later inventory"
let later = state.beginSave()!
state.completeSave(later, succeeded: true)
state.reconcile(["First", "New profile", "Second"])
precondition(state.selectedName == "New profile")
state.reconcile(["First", "Later inventory", "New profile", "Second"])
precondition(state.selectedName == "Later inventory")

state.draftName = "Rejected"
let rejected = state.beginSave()!
state.completeSave(rejected, succeeded: false)
state.reconcile(["First", "Later inventory", "Second"])
precondition(state.selectedName == "Later inventory" && state.savedNameToSelect == nil)
state.selectedName = "Second"
state.reconcile(["First", "Later inventory", "Rejected", "Second"])
precondition(state.selectedName == "Second", "failed save redirected a later external refresh")
precondition(state.draftName == "Rejected", "failed save discarded the editable name")

state.draftName = "First"
let dismissed = state.beginSave()!
state.invalidateSave()
state.draftName = "Second"
let current = state.beginSave()!
state.completeSave(dismissed, succeeded: true)
precondition(state.pendingSave == current && state.savedNameToSelect == nil,
             "dismissed sheet completion took ownership of a later request")
state.completeSave(current, succeeded: true)
state.reconcile(["First", "Second"])
precondition(state.selectedName == "Second")
state.reconcile(["First"])
precondition(state.selectedName == "First", "deleted selection did not reconcile")
state.reconcile([])
precondition(state.selectedName.isEmpty, "empty inventory retained a load/delete target")
state.reconcile(["Restored"])
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
