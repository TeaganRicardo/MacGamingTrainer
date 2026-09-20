import SwiftUI
import AppKit

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
    @State private var capturing: ShortcutAction?
    @State private var keyMonitor: Any?

    var body: some View {
        TrainerSheetScaffold(title: "快捷键设置", width: 560) {
            EmptyView()
        } content: {
            Text("点击任一快捷键后直接按下新的组合键。Esc 取消捕获；支持 Control / Option / Shift / Command 与数字、字母、方向键、F 键等组合。")
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            ForEach(ShortcutAction.uiOrder) { action in
                HStack {
                    Text(action.title)
                    Spacer()
                    Button {
                        beginCapture(action)
                    } label: {
                        Text(capturing == action ? "按下新快捷键…" : model.shortcutText(action))
                            .font(.system(.body, design: .monospaced))
                            .frame(minWidth: 110)
                    }
                    .buttonStyle(.bordered)
                }
            }
            if !model.shortcutError.isEmpty {
                Text(model.shortcutError).foregroundStyle(theme.warning).font(.caption)
            }
        } footer: {
            HStack {
                Spacer()
                Button("完成") {
                    stopCapture()
                    model.shortcutSettingsPresented = false
                }
                .keyboardShortcut(.defaultAction)
            }
        }
        .onDisappear { stopCapture() }
    }

    private func beginCapture(_ action: ShortcutAction) {
        stopCapture()
        capturing = action
        model.shortcutError = ""
        keyMonitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { event in
            if event.keyCode == 53 {
                DispatchQueue.main.async { stopCapture() }
                return nil
            }
            guard let chord = HotkeyChord.capture(event) else {
                model.shortcutError = "无法识别该按键，请换一个组合。"
                return nil
            }
            DispatchQueue.main.async {
                model.setShortcut(action: action, chord: chord)
                stopCapture()
            }
            return nil
        }
    }

    private func stopCapture() {
        if let keyMonitor {
            NSEvent.removeMonitor(keyMonitor)
            self.keyMonitor = nil
        }
        capturing = nil
    }
}
