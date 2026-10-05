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
    let supportsSaveManagement: Bool
}

struct TrainerManagementActions {
    let openSaveManagement: (() -> Void)?

    static let none = TrainerManagementActions(openSaveManagement: nil)
}

private struct TrainerManagementActionsKey: EnvironmentKey {
    static let defaultValue = TrainerManagementActions.none
}

extension EnvironmentValues {
    var trainerManagementActions: TrainerManagementActions {
        get { self[TrainerManagementActionsKey.self] }
        set { self[TrainerManagementActionsKey.self] = newValue }
    }
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
    /// Language-neutral operation identity shown while a request is in flight.
    var operation: TrainerTextToken { get }
    /// Language-neutral presentation tokens. The Host resolves them against the
    /// selected module's presentation layer, so a module never embeds localized
    /// copy in its observable state and a language switch re-renders without a
    /// backend round trip.
    var statusTitle: TrainerTextToken { get }
    var connectionDetailText: TrainerTextToken { get }
    var hostActionsEnabled: Bool { get }

    func toggleConnectionFromHost()
    func connectAutomaticallyFromHost(targetJustLaunched: Bool)
    func refreshFromHost()
    func hostDidBecomeActive()
    func restartBackendFromHost()
    func prepareForTermination(completion: @escaping (Bool) -> Void)
}

extension TrainerHostModel {
    /// Automatic target connection carries only generic lifecycle context.
    /// Modules that do not care about launch timing keep the normal toggle path.
    func connectAutomaticallyFromHost(targetJustLaunched: Bool) {
        toggleConnectionFromHost()
    }

    /// App activation is a safe point for game modules to perform an optional
    /// foreground-only refresh. The default is deliberately a no-op because
    /// not every integration needs or can afford a live target boundary.
    func hostDidBecomeActive() {}
}

/// Game modules supply business content and game-specific actions. The host
/// always owns the shell/sidebar/header, so global chrome/theme changes apply
/// to every game without relying on module authors to opt in.
protocol TrainerGameModule {
    associatedtype Model: TrainerHostModel
    associatedtype ContentView: View
    associatedtype SidebarActions: View
    associatedtype HeaderActions: View
    associatedtype FeedbackView: View = EmptyView
    associatedtype ManagementCommands: Commands

    static var descriptor: GameModuleDescriptor { get }
    static var presentation: TrainerGamePresentation { get }
    static func makeModel(session: TrainerBackendSession) -> Model
    static func makeContent(model: Model) -> ContentView
    static func makeSidebarActions(model: Model) -> SidebarActions
    static func makeHeaderActions(model: Model) -> HeaderActions
    static func makeFeedback(model: Model) -> FeedbackView
    static func makeManagementCommands(model: Model, localization: TrainerLocalizationStore) -> ManagementCommands

    /// Key namespace this module owns. Registering it lets the Host resolve the
    /// model's tokens without Core learning any module vocabulary.
    static var presentationKeyPrefix: String { get }

    /// Resolve one of this module's own keys. Returning the key itself for an
    /// unknown entry keeps a missing translation visible instead of blank.
    static func presentationText(
        key: String,
        arguments: [String],
        language: TrainerPresentationLanguage
    ) -> String
}

extension TrainerGameModule {
    /// A module without its own namespace has no module-owned text to resolve.
    public static var presentationKeyPrefix: String { "" }

    /// Modules opt into viewport feedback without changing the shared Host or
    /// adding another session. The default contributes no view or empty space.
    static func makeFeedback(model: Model) -> EmptyView { EmptyView() }
}

struct TrainerEmptyCommands: Commands {
    var body: some Commands {
        CommandGroup(after: .appInfo) { EmptyView() }
    }
}
