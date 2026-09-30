from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
view_path = ROOT / "Sources/Core/Save/TrainerSaveManagerView.swift"
host_path = ROOT / "Sources/Core/Host/TrainerHost.swift"
app_path = ROOT / "Sources/App.swift"

assert view_path.is_file(), "generic save manager view missing"
view = view_path.read_text(encoding="utf-8")
host = host_path.read_text(encoding="utf-8")
app = app_path.read_text(encoding="utf-8")

for token in (
    "struct TrainerSaveManagerView",
    "@EnvironmentObject private var localization: TrainerLocalizationStore",
    "@State private var selectedIDs: Set<String>",
    "@State private var editingID:",
    "TrainerInlineNameEditor",
    ".onTapGesture(count: 2)",
    'TrainerPillBadge(text: localization.localized("host.save.hotBackup")',
    "TrainerOverflowMenu",
    'Label(localization.localized("host.showInFinder")',
    'Label(localization.localized("host.delete")',
    'Button(localization.localized("host.restore"))',
    "TrainerCheckboxControl(",
    'title: localization.localized("host.save.preserveCurrent")',
    "deleteIDs = selectedIDs",
    "model.delete(ids: ids)",
    "model.reveal(id: snapshot.id)",
    "model.restore(id:",
    "LazyVStack",
    'localization.localized("host.save.fileCount", arguments:',
    'localization.presentation(model.error, arguments: model.errorArguments)',
    'localization.presentation(model.notice, arguments: model.noticeArguments)',
    'snapshot.displayName(for: localization.language.rawValue)',
    'snapshot.displayDetails(for: localization.language.rawValue)',
):
    assert token in view, token

assert "NavigationSplitView" not in view
assert "Inspector" not in view
assert "Hades" not in view
assert "Timer.scheduledTimer" not in view
assert "@FocusState" not in view
assert "pending.indeterminate" in view
assert 'localization.localized("host.save.pendingIndeterminate")' in view
assert '"host.clearStatus" : "host.cancel"' in view
assert "if !model.recoveryPaths.isEmpty" in view
assert 'localization.localized("host.save.recoveryCopiesWarning")' in view
assert "model.revealRecoveryCopies()" in view
assert 'model.recoveryPaths.joined(separator: "\\n")' in view

for token in (
    "@StateObject private var saveManager: TrainerSaveManagerModel",
    "Module.descriptor.supportsSaveManagement",
    "TrainerSaveManagerView(model: saveManager",
    "init(model: Module.Model, session: TrainerBackendSession)",
):
    assert token in host, token

assert "TrainerHostView<ActiveGameModule>(model: model, session: backendSession)" in app

print("core_save_ui_round20_ok")
