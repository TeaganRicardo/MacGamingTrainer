import Foundation
import SwiftUI

struct GameModuleDescriptor: Identifiable, Hashable {
    let id: String
    let displayName: String
    let backendGameID: String
    let targetProcessName: String
    let targetBundleIdentifier: String
    let expectedHostProtocolVersion: Int
    let expectedModuleProtocolVersion: Int
}

struct TrainerGamePresentation: Hashable {
    let sidebarIconSystemName: String
    let platformLabel: String
    let headerTitle: String

    init(sidebarIconSystemName: String = "gamecontroller.fill", platformLabel: String = "", headerTitle: String) {
        self.sidebarIconSystemName = sidebarIconSystemName
        self.platformLabel = platformLabel
        self.headerTitle = headerTitle
    }
}

/// The App owns application lifecycle. A game model only prepares its own
/// runtime for termination and reports whether the host may quit.
protocol TrainerHostModel: ObservableObject {
    var backendAvailable: Bool { get }
    var busy: Bool { get }
    var connected: Bool { get }
    var operation: String { get }
    var statusTitle: String { get }
    var connectionDetailText: String { get }
    var hostActionsEnabled: Bool { get }

    func toggleConnectionFromHost()
    func refreshFromHost()
    func restartBackendFromHost()
    func disableAllFromHost()
    func openLog()
    func prepareForTermination(completion: @escaping (Bool) -> Void)
}

/// Game modules supply business content and game-specific actions. The host
/// always owns the shell/sidebar/header, so global chrome/theme changes apply
/// to every game without relying on module authors to opt in.
protocol TrainerGameModule {
    associatedtype Model: TrainerHostModel
    associatedtype ContentView: View
    associatedtype SidebarActions: View
    associatedtype HeaderActions: View

    static var descriptor: GameModuleDescriptor { get }
    static var presentation: TrainerGamePresentation { get }
    static func makeModel() -> Model
    static func makeContent(model: Model) -> ContentView
    static func makeSidebarActions(model: Model) -> SidebarActions
    static func makeHeaderActions(model: Model) -> HeaderActions
}
