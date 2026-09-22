import SwiftUI

struct Hades2SidebarActions: View {
    @ObservedObject var model: Hades2TrainerModel

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Button { model.shortcutSettingsPresented = true } label: { Label("快捷键设置", systemImage: "keyboard") }
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


struct Hades2ManagementCommands: Commands {
    @ObservedObject var model: Hades2TrainerModel

    var body: some Commands {
        CommandMenu("训练器") {
            Button("刷新状态") { model.refreshFromHost() }
                .disabled(model.busy)
            Button("全部关闭") { model.disableAll() }
                .disabled(model.busy || !model.connected)
            Divider()
            Button("快捷键设置") { model.shortcutSettingsPresented = true }
            Button("查看日志") { model.openLog() }
        }
    }
}
