import SwiftUI

final class ReferenceFixtureModel: ObservableObject, TrainerHostModel {
    @Published var backendAvailable = true
    @Published var busy = false
    @Published var connected = false
    @Published var enabled = false
    @Published var operation = ""

    var statusTitle: String { connected ? "已连接" : "尚未连接" }
    var connectionDetailText: String { "Reference fixture" }
    var hostActionsEnabled: Bool { true }

    func toggleConnectionFromHost() {
        connected.toggle()
    }

    func refreshFromHost() {}

    func restartBackendFromHost() {
        backendAvailable = true
    }

    func disableAllFromHost() {
        enabled = false
    }

    func openLog() {}

    func prepareForTermination(completion: @escaping (Bool) -> Void) {
        completion(true)
    }
}

struct ReferenceFixtureContent: View {
    @ObservedObject var model: ReferenceFixtureModel

    var body: some View {
        TrainerFeatureToggleRow(
            title: "Reference Feature",
            icon: "checkmark.circle",
            state: TrainerFeatureControlState(
                isOn: model.enabled,
                isInteractive: true,
                canEditValue: false,
                opacity: 1,
                indicatorColor: .accentColor,
                helpText: "",
                isWarning: false
            ),
            shortcutText: nil
        ) {
            model.enabled.toggle()
        }
    }
}

struct ReferenceFixtureGameModule: TrainerGameModule {
    static let presentation = TrainerGamePresentation(
        sidebarIconSystemName: "checkmark.seal",
        headerTitle: "REFERENCE"
    )

    static func makeModel(session: TrainerBackendSession) -> ReferenceFixtureModel {
        _ = session
        return ReferenceFixtureModel()
    }

    static func makeContent(model: ReferenceFixtureModel) -> ReferenceFixtureContent {
        ReferenceFixtureContent(model: model)
    }

    static func makeSidebarActions(model: ReferenceFixtureModel) -> some View {
        EmptyView()
    }

    static func makeHeaderActions(model: ReferenceFixtureModel) -> some View {
        EmptyView()
    }
}
