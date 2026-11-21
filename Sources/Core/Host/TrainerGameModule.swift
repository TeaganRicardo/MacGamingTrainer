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

/// Services for one persistent game context, scoped to its module descriptor.
@MainActor
package final class TrainerModuleServices {
    package let descriptor: GameModuleDescriptor
    package let session: TrainerBackendSession
    package let logSink: TrainerLogSink
    package internal(set) var targetObservation: TrainerTargetObservation
    package var backendStatus: TrainerBackendStatus { session.currentStatus }

    init(descriptor: GameModuleDescriptor, session: TrainerBackendSession,
         logSink: TrainerLogSink, targetObservation: TrainerTargetObservation) {
        self.descriptor = descriptor
        self.session = session
        self.logSink = logSink
        self.targetObservation = targetObservation
    }

    package func makeHotkeys(
        registrationChanged: @escaping @MainActor (TrainerHotkeyRegistrationFailure?) -> Void = { _ in },
        action: @escaping @MainActor (String) -> Void
    ) -> GlobalHotkeys {
        GlobalHotkeys(gameID: descriptor.id, registrationChanged: registrationChanged, action: action)
    }
}

package enum TrainerHostConnectReason: Equatable {
    case manual
    case automatic(targetJustLaunched: Bool)
}

/// The module identifies target-bound payloads without exposing its wire
/// vocabulary to Core. Sparse and disconnected state can still be bound to
/// the lifetime in which the request started.
package enum TrainerBackendPayloadTarget {
    case independent
    case lifetime
    case process(identifier: Int?)
}

/// The App owns application lifecycle. A game model only prepares its own
/// runtime for committed termination after the Host has drained all contexts.
@MainActor
package protocol TrainerHostModel: ObservableObject {
    var connected: Bool { get }
    /// Language-neutral presentation tokens. The Host resolves them against the
    /// selected module's presentation layer, so a module never embeds localized
    /// copy in its observable state and a language switch re-renders without a
    /// backend round trip.
    var statusTitle: TrainerTextToken { get }
    var connectionDetailText: TrainerTextToken { get }
    var hostActionsEnabled: Bool { get }
    /// Optional module-owned launch operation; the Host owns its card placement.
    var launchActionFromHost: (@MainActor () -> Void)? { get }

    func connectFromHost(reason: TrainerHostConnectReason)
    func disconnectFromHost()
    func refreshFromHost()
    func hostDidBecomeActive()
    func hostTargetLifetimeChanged(observation: TrainerTargetObservation)
    /// Initial module reads follow the Context's worker startup.
    func backendDidStart()
    func backendWillRestart()
    func backendDidStop()
    /// Every module declares which target a payload describes; there is no
    /// default. `.independent` applies the payload whatever target is running,
    /// so use it only for state that never depends on one. `.lifetime` drops a
    /// reply whose request began under an earlier target observation, and
    /// `.process` also drops one that reports another process identifier or
    /// arrives while no target is running. Dropped payloads go to
    /// `applyStaleBackendPayload`, which should re-read or keep only state
    /// that does not depend on the target.
    func backendPayloadTarget(_ payload: [String: Any]) -> TrainerBackendPayloadTarget
    func applyBackendPayload(_ payload: [String: Any])
    func applyStaleBackendPayload(_ payload: [String: Any])
    func beginTerminationFromHost()
    func prepareForTermination(completion: @escaping () -> Void)
}

extension TrainerHostModel {
    package func beginTerminationFromHost() {}
    package func prepareForTermination(completion: @escaping () -> Void) { completion() }
    package var launchActionFromHost: (@MainActor () -> Void)? { nil }
    package func backendDidStart() {}
    package func backendWillRestart() {}
    package func backendDidStop() {}
    package func applyBackendPayload(_ payload: [String: Any]) {}
    /// A late reply may still carry an action receipt or durable metadata.
    package func applyStaleBackendPayload(_ payload: [String: Any]) {}

    /// App activation is a safe point for game modules to perform an optional
    /// foreground-only refresh. The default is deliberately a no-op because
    /// not every integration needs or can afford a live target boundary.
    package func hostDidBecomeActive() {}

    /// Definitive target launch/exit invalidates game-owned observations from
    /// the prior OS process lifetime. Modules without such state may ignore it.
    package func hostTargetLifetimeChanged(observation: TrainerTargetObservation) {}
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
    @MainActor static func makeModel(services: TrainerModuleServices) -> Model
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
