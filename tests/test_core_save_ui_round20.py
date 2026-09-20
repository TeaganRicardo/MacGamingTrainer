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
    "@State private var selectedIDs: Set<String>",
    "@State private var editingID:",
    "TrainerInlineNameEditor",
    ".onTapGesture(count: 2)",
    'TrainerPillBadge(text: "热备份"',
    "TrainerOverflowMenu",
    'Label("在 Finder 中显示"',
    'Label("删除"',
    'Button("恢复")',
    'TrainerCheckboxControl(',
    'title: "恢复前保留当前存档"',
    "deleteIDs = selectedIDs",
    "model.delete(ids: ids)",
    "model.reveal(id: snapshot.id)",
    "model.restore(id:",
    "LazyVStack",
):
    assert token in view, token

assert "NavigationSplitView" not in view
assert "Inspector" not in view
assert "Hades" not in view
assert "Timer.scheduledTimer" not in view
assert "@FocusState" not in view

for token in (
    "@StateObject private var saveManager: TrainerSaveManagerModel",
    "Module.descriptor.supportsSaveManagement",
    "TrainerSaveManagerView(model: saveManager",
    "init(model: Module.Model, session: TrainerBackendSession)",
):
    assert token in host, token

assert "TrainerHostView<ActiveGameModule>(model: model, session: backendSession)" in app

print("core_save_ui_round20_ok")
