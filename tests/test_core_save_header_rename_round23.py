from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
view = (ROOT / "Sources/Core/Save/TrainerSaveManagerView.swift").read_text(encoding="utf-8")

header = view[view.index('TrainerSheetScaffold(title: "存档管理"'):view.index('} content: {')]
assert 'Label("创建备份", systemImage: "plus")' in header
assert 'Label("刷新", systemImage: "arrow.clockwise")' in header
assert header.index('Label("创建备份"') < header.index('Label("刷新"')

section = view[view.index('TrainerSection(title: "备份历史"'):view.index('} footer: {')]
assert 'Label("创建备份", systemImage: "plus")' not in section

menu = view[view.index('TrainerOverflowMenu(enabled: !model.busy)'):view.index('    private var deleteTitle')]
assert 'Label("重命名", systemImage: "pencil")' in menu
assert 'beginRename(snapshot)' in menu

assert '.onTapGesture { finishRenameFromPointer() }' in view
assert 'private func finishRenameFromPointer()' in view
assert 'NSApp.keyWindow?.makeFirstResponder(nil)' in view

print("core_save_header_rename_round23_ok")
