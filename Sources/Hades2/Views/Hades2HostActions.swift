import SwiftUI

struct Hades2SidebarActions: View {
    @ObservedObject var model: Hades2TrainerModel

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Button { model.shortcutSettingsPresented = true } label: { Label("快捷键设置", systemImage: "keyboard") }
            Button {
                model.saveManagerPresented = true
                model.refreshBackups()
            } label: { Label("存档管理", systemImage: "externaldrive") }
            .disabled(!model.backendAvailable || model.exiting)
            Button { model.openLog() } label: { Label("查看运行日志", systemImage: "doc.text") }
        }
    }
}

struct Hades2HeaderActions: View {
    @ObservedObject var model: Hades2TrainerModel

    var body: some View {
        Button { model.launchGame() } label: {
            Label("启动游戏", systemImage: "play.fill").padding(.horizontal, 7).padding(.vertical, 5)
        }
        .buttonStyle(.bordered)
        .disabled(model.busy || model.exiting)
    }
}
