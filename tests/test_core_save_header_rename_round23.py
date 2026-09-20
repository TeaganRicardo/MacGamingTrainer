from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
view = (ROOT / "Sources/Core/Save/TrainerSaveManagerView.swift").read_text(encoding="utf-8")
controls = (ROOT / "Sources/Core/UI/Components/TrainerListControls.swift").read_text(encoding="utf-8")

header = view[view.index('TrainerSheetScaffold(title: "存档管理"'):view.index('} content: {')]
assert 'Label("刷新", systemImage: "arrow.clockwise")' in header
assert 'TrainerPrimaryActionButton(' in header
assert 'title: "创建备份"' in header
assert header.index('Label("刷新"') < header.index('title: "创建备份"')

footer = view[view.index('} footer: {'):view.index('.interactiveDismissDisabled')]
assert 'TrainerPrimaryActionButton(' in footer
assert 'title: "完成"' in footer

menu = view[view.index('TrainerOverflowMenu(enabled: !model.busy)'):view.index('    private var deleteTitle')]
assert 'Label("重命名", systemImage: "pencil")' in menu
assert 'beginRename(snapshot)' in menu

assert 'TrainerInlineNameEditor(' in view
assert '@FocusState' not in view
assert 'NSApp.keyWindow?.makeFirstResponder(nil)' not in view
assert '.onTapGesture { finishRenameFromPointer() }' not in view
assert 'pendingRenameNames' in view
assert '.buttonStyle(.borderedProminent)' not in view

assert 'struct TrainerPrimaryActionButton' in controls
assert '.buttonStyle(.borderedProminent)' in controls
assert '.tint(theme.accent)' in controls
assert 'struct TrainerInlineNameEditor' in controls
assert 'NSEvent.addLocalMonitorForEvents' in controls

print("core_save_header_rename_round23_ok")
