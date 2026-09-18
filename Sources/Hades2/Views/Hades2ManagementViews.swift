import SwiftUI

struct Hades2SaveManagerView: View {
    @ObservedObject var model: Hades2TrainerModel
    @Environment(\.trainerTheme) private var theme
    @State private var selectedBackup = ""
    @State private var backupRename = ""
    @State private var confirmRestore = false
    @State private var confirmDelete = false

    var body: some View {
        TrainerSheetScaffold(title: "存档管理", icon: "externaldrive.fill", width: 720) {
            if model.saveManagerBusy { ProgressView().controlSize(.small) }
            Button("打开备份目录") { model.openBackupFolder() }
                .disabled(model.saveManagerBusy || !model.backendAvailable)
            Button("刷新") { model.refreshBackups() }
                .disabled(model.saveManagerBusy)
        } content: {
            Text("创建备份可在游戏运行时进行。运行中选择恢复会暂存任务；退出 Hades II 后 Trainer 会自动执行校验恢复，并在恢复前创建安全备份。")
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)

            if let pending = model.pendingRestoreID {
                TrainerInlineNotice(color: theme.deferred) {
                    HStack(spacing: 10) {
                        Image(systemName: "clock.arrow.circlepath").foregroundStyle(theme.deferred)
                        Text("已暂存恢复：\(model.backups.first(where: { $0.id == pending })?.name ?? pending)。等待 Hades II 退出。")
                            .font(.caption)
                            .foregroundStyle(theme.deferred)
                        Spacer()
                        Button("取消") { model.cancelStagedRestore() }.controlSize(.small)
                    }
                }
            }

            if !model.error.isEmpty {
                TrainerMessageBanner(text: model.error, icon: "exclamationmark.triangle", color: theme.warning)
            } else if !model.notice.isEmpty {
                TrainerMessageBanner(text: model.notice, icon: "checkmark.circle", color: theme.success)
            }

            ScrollView {
                LazyVStack(spacing: 8) {
                    if model.backups.isEmpty {
                        TrainerEmptyState(text: "暂无备份。可以先创建当前存档备份。")
                    }
                    ForEach(model.backups) { backup in
                        TrainerSelectableListRow(
                            selected: selectedBackup == backup.id,
                            enabled: !model.saveManagerBusy,
                            action: { selectedBackup = backup.id }
                        ) {
                            HStack(alignment: .top, spacing: 12) {
                                Image(systemName: selectedBackup == backup.id ? "checkmark.circle.fill" : "circle")
                                    .foregroundStyle(theme.accent)
                                VStack(alignment: .leading, spacing: 5) {
                                    HStack(spacing: 8) {
                                        Text(backup.name).font(.subheadline.weight(.semibold)).lineLimit(1)
                                        if backup.hotBackup {
                                            TrainerPillBadge(text: "热备份", color: theme.info)
                                        }
                                    }
                                    let runText = backup.runCount.map { "Run \($0)" } ?? "Run —"
                                    Text("\(backup.createdAt) · \(runText) · \(backup.fileCount) 个文件")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                        .lineLimit(2)
                                    if !backup.valid {
                                        Text(backup.error.isEmpty ? "备份校验失败，无法恢复" : backup.error)
                                            .font(.caption)
                                            .foregroundStyle(theme.warning)
                                    }
                                }
                                Spacer()
                            }
                        }
                    }
                }
            }
            .frame(minHeight: 220, maxHeight: 360)

            HStack(spacing: 10) {
                TextField("备份名称", text: $backupRename)
                    .textFieldStyle(.roundedBorder)
                    .disabled(selectedBackup.isEmpty || model.saveManagerBusy)
                    .frame(maxWidth: .infinity)
                Button("重命名") { model.renameBackup(selectedBackup, name: backupRename) }
                    .disabled(model.saveManagerBusy || selectedBackup.isEmpty || backupRename.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                Button("在文件夹中显示") { model.openBackupFolder(selectedBackup) }
                    .disabled(model.saveManagerBusy || selectedBackup.isEmpty)
                Button(role: .destructive) { confirmDelete = true } label: { Label("删除", systemImage: "trash") }
                    .disabled(model.saveManagerBusy || selectedBackup.isEmpty)
            }
        } footer: {
            HStack {
                Button("创建备份") { model.createBackup() }
                    .disabled(model.saveManagerBusy || !model.backendAvailable)
                Spacer()
                Button("完成") { model.saveManagerPresented = false }
                    .disabled(model.saveManagerBusy)
                Button("恢复所选") { confirmRestore = true }
                    .buttonStyle(.borderedProminent)
                    .disabled(model.saveManagerBusy || !model.backendAvailable || !model.backups.contains(where: { $0.id == selectedBackup && $0.valid }))
            }
        }
        .interactiveDismissDisabled(model.saveManagerBusy)
        .alert("恢复所选存档？", isPresented: $confirmRestore) {
            Button("取消", role: .cancel) { }
            Button("备份当前并恢复") { model.restoreBackup(selectedBackup) }
        } message: {
            Text("将恢复“\(model.backups.first(where: { $0.id == selectedBackup })?.name ?? selectedBackup)”。若游戏仍在运行，会先暂存任务并在退出后自动执行。")
        }
        .alert("删除所选备份？", isPresented: $confirmDelete) {
            Button("取消", role: .cancel) { }
            Button("永久删除", role: .destructive) { model.deleteBackup(selectedBackup) }
        } message: {
            Text("将永久删除“\(model.backups.first(where: { $0.id == selectedBackup })?.name ?? selectedBackup)”。此操作不会修改当前游戏存档。")
        }
        .onChange(of: model.backups.map(\.id), initial: true) { _, ids in
            if !ids.contains(selectedBackup) {
                selectedBackup = ""
                backupRename = ""
            }
        }
        .onChange(of: selectedBackup, initial: true) { _, id in
            backupRename = model.backups.first(where: { $0.id == id })?.name ?? ""
        }
    }
}

struct Hades2ProfileManagerView: View {
    @ObservedObject var model: Hades2TrainerModel
    @Binding var isPresented: Bool
    @State private var profileName = ""
    @State private var selectedProfile = ""

    var body: some View {
        TrainerSheetScaffold(title: "自定义配置", icon: "slider.horizontal.3", width: 620) {
            Button("刷新") { model.listProfiles() }.disabled(model.busy)
        } content: {
            Text("只保存你创建的自定义配置，不内置任何预设。配置包含功能开关、倍率、属性/资源/元素锁、祝福稀有度、下一房奖励和快捷键。")
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            HStack(spacing: 10) {
                TextField("新配置名称", text: $profileName).textFieldStyle(.roundedBorder)
                Button("保存当前状态") {
                    model.saveProfile(profileName)
                    selectedProfile = profileName.trimmingCharacters(in: .whitespacesAndNewlines)
                }
                .disabled(model.busy || profileName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
            Divider()
            if model.profiles.isEmpty {
                TrainerEmptyState(text: "暂无自定义配置。保存后会出现在这里。")
            } else {
                Picker("配置", selection: $selectedProfile) {
                    ForEach(model.profiles) { profile in
                        Text(profile.updatedAt.isEmpty ? profile.name : "\(profile.name) · \(profile.updatedAt)").tag(profile.name)
                    }
                }
                HStack {
                    Button("载入") { model.loadProfile(selectedProfile) }
                        .buttonStyle(.borderedProminent)
                        .disabled(model.busy || selectedProfile.isEmpty)
                    Button(role: .destructive) { model.deleteProfile(selectedProfile) } label: { Label("删除", systemImage: "trash") }
                        .disabled(model.busy || selectedProfile.isEmpty)
                    Spacer()
                }
            }
        } footer: {
            HStack { Spacer(); Button("完成") { isPresented = false } }
        }
        .onChange(of: model.profiles.map(\.name), initial: true) { _, names in
            if !names.contains(selectedProfile) {
                selectedProfile = names.first ?? ""
            }
        }
    }
}

struct Hades2DiagnosticsView: View {
    @ObservedObject var model: Hades2TrainerModel
    @Binding var isPresented: Bool
    @Environment(\.trainerTheme) private var theme

    var body: some View {
        TrainerSheetScaffold(title: "运行自检", icon: "stethoscope", width: 700) {
            Text("\(model.diagnosticsPassed)/\(model.diagnosticsTotal)").font(.headline).monospacedDigit()
            Button { model.exportDiagnostics() } label: { Label("导出诊断包", systemImage: "square.and.arrow.up") }
                .disabled(model.busy || !model.backendAvailable)
            Button("重新检测") { model.runDiagnostics() }.disabled(model.busy)
        } content: {
            Text("检测开发工具、协议版本、游戏安装/进程、Lua 连接与运行时 revision。诊断包仅包含状态、自检结果、symbols.json 与 trainer.log 尾部，不包含存档或自定义 Profile。")
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            ScrollView {
                LazyVStack(spacing: 8) {
                    ForEach(model.diagnostics) { check in
                        TrainerListCard {
                            HStack(alignment: .top, spacing: 12) {
                                Image(systemName: check.ok ? "checkmark.circle.fill" : "xmark.circle.fill")
                                    .foregroundStyle(check.ok ? theme.success : theme.warning)
                                VStack(alignment: .leading, spacing: 3) {
                                    Text(check.name).font(.subheadline.weight(.semibold))
                                    if !check.detail.isEmpty {
                                        Text(check.detail).font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
                                    }
                                }
                                Spacer()
                            }
                        }
                    }
                }
            }
            .frame(minHeight: 260, maxHeight: 430)
        } footer: {
            HStack { Spacer(); Button("完成") { isPresented = false } }
        }
    }
}

struct Hades2ShortcutSettingsView: View {
    @ObservedObject var model: Hades2TrainerModel
    @Environment(\.trainerTheme) private var theme

    var body: some View {
        TrainerSheetScaffold(title: "快捷键设置", width: 490) {
            EmptyView()
        } content: {
            Text("全局快捷键使用 Control + Option + 数字。")
                .foregroundStyle(.secondary)
            ForEach(ShortcutAction.uiOrder) { action in
                HStack {
                    Text(action.title)
                    Spacer()
                    Text("⌃ Control  ⌥ Option +").foregroundStyle(.secondary)
                    Picker("按键", selection: Binding(
                        get: { model.shortcutDigit(action) },
                        set: { model.setShortcut(action: action, digit: $0) }
                    )) {
                        ForEach(0..<10) { Text(String($0)).tag($0) }
                    }
                    .labelsHidden()
                    .frame(width: 65)
                }
            }
            if !model.shortcutError.isEmpty {
                Text(model.shortcutError).foregroundStyle(theme.warning).font(.caption)
            }
        } footer: {
            HStack {
                Spacer()
                Button("完成") { model.shortcutSettingsPresented = false }.keyboardShortcut(.defaultAction)
            }
        }
    }
}
