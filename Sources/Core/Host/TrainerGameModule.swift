import Foundation
import SwiftUI

package struct GameModuleDescriptor: Identifiable, Hashable, Sendable {
    package let id: String
    package let displayName: String
    package let targetProcessName: String
    package let targetBundleIdentifier: String
    let targetExecutablePathSuffix: String
    package let expectedHostProtocolVersion: Int
    package let expectedModuleProtocolVersion: Int
    let supportsSaveManagement: Bool

    package init(id: String, displayName: String,
         targetProcessName: String, targetBundleIdentifier: String,
         targetExecutablePathSuffix: String = "",
         expectedHostProtocolVersion: Int, expectedModuleProtocolVersion: Int,
         supportsSaveManagement: Bool) {
        self.id = id
        self.displayName = displayName
        self.targetProcessName = targetProcessName
        self.targetBundleIdentifier = targetBundleIdentifier
        self.targetExecutablePathSuffix = targetExecutablePathSuffix
        self.expectedHostProtocolVersion = expectedHostProtocolVersion
        self.expectedModuleProtocolVersion = expectedModuleProtocolVersion
        self.supportsSaveManagement = supportsSaveManagement
    }
}

package struct TrainerManagementActions {
    package let openSaveManagement: (() -> Void)?

    static let none = TrainerManagementActions(openSaveManagement: nil)
}

private struct TrainerManagementActionsKey: EnvironmentKey {
    static let defaultValue = TrainerManagementActions.none
}

extension EnvironmentValues {
    package var trainerManagementActions: TrainerManagementActions {
        get { self[TrainerManagementActionsKey.self] }
        set { self[TrainerManagementActionsKey.self] = newValue }
    }
}

package struct TrainerGamePresentation: Hashable {
    let sidebarIconSystemName: String
    let platformLabel: String
    let headerTitle: String

    package init(sidebarIconSystemName: String = "gamecontroller.fill", platformLabel: String = "", headerTitle: String) {
        self.sidebarIconSystemName = sidebarIconSystemName
        self.platformLabel = platformLabel
        self.headerTitle = headerTitle
    }
}

/// The App owns application lifecycle. A game model only prepares its own
/// runtime for committed termination after the Host has drained all contexts.
@MainActor
package protocol TrainerHostModel: ObservableObject {
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
    /// Optional module-owned launch operation; the Host owns its card placement.
    var launchActionFromHost: (@MainActor () -> Void)? { get }

    func toggleConnectionFromHost()
    func connectAutomaticallyFromHost(targetJustLaunched: Bool)
    func refreshFromHost()
    func hostDidBecomeActive()
    func hostTargetLifetimeChanged(running: Bool)
    func hostTargetLifetimeChanged(observation: TrainerTargetObservation)
    func restartBackendFromHost()
    func beginTerminationFromHost()
    func prepareForTermination(completion: @escaping () -> Void)
}

extension TrainerHostModel {
    package func beginTerminationFromHost() {}
    package var launchActionFromHost: (@MainActor () -> Void)? { nil }
    /// Automatic target connection carries only generic lifecycle context.
    /// Modules that do not care about launch timing keep the normal toggle path.
    package func connectAutomaticallyFromHost(targetJustLaunched: Bool) {
        toggleConnectionFromHost()
    }

    /// App activation is a safe point for game modules to perform an optional
    /// foreground-only refresh. The default is deliberately a no-op because
    /// not every integration needs or can afford a live target boundary.
    package func hostDidBecomeActive() {}

    /// Definitive target launch/exit invalidates game-owned observations from
    /// the prior OS process lifetime. Modules without such state may ignore it.
    package func hostTargetLifetimeChanged(running: Bool) {}

    /// Rich target identity is available to modules that own process-lifetime
    /// diagnostics. Existing modules can continue consuming only presence.
    package func hostTargetLifetimeChanged(observation: TrainerTargetObservation) {
        hostTargetLifetimeChanged(running: observation.isRunning)
    }
}

/// Game modules supply business content and game-specific actions. The host
/// always owns the shell/sidebar/header, so global chrome/theme changes apply
/// to every game without relying on module authors to opt in.
package protocol TrainerGameModule {
    associatedtype Model: TrainerHostModel
    associatedtype ContentView: View
    associatedtype SidebarActions: View
    associatedtype HeaderActions: View
    associatedtype FeedbackView: View = EmptyView
    associatedtype ManagementCommands: Commands

    static var descriptor: GameModuleDescriptor { get }
    static var presentation: TrainerGamePresentation { get }
    @MainActor static func makeModel(session: TrainerBackendSession) -> Model
    @MainActor static func makeContent(model: Model) -> ContentView
    @MainActor static func makeSidebarActions(model: Model) -> SidebarActions
    @MainActor static func makeHeaderActions(model: Model) -> HeaderActions
    @MainActor static func makeFeedback(model: Model) -> FeedbackView
    @MainActor static func makeManagementCommands(model: Model, localization: TrainerLocalizationStore) -> ManagementCommands

    /// Optional game-owned workbench for a generic verified backup row.
    @MainActor static var managedBackupEditor: (@MainActor (Model, TrainerSaveSnapshot) -> TrainerToolWindowContent)? { get }

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
    @MainActor package static var managedBackupEditor: (@MainActor (Model, TrainerSaveSnapshot) -> TrainerToolWindowContent)? { nil }
    /// A module without its own namespace has no module-owned text to resolve.
    package static var presentationKeyPrefix: String { "" }

    /// Modules opt into viewport feedback without changing the shared Host or
    /// adding another session. The default contributes no view or empty space.
    @MainActor package static func makeFeedback(model: Model) -> EmptyView { EmptyView() }
}

package struct TrainerEmptyCommands: Commands {
    package init() {}

    package var body: some Commands {
        CommandGroup(after: .appInfo) { EmptyView() }
    }
}
