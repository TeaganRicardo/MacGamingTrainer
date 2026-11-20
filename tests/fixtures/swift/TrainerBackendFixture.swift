import Foundation
@testable import TrainerCore

/// Model-level journeys drive their own synthetic replies. Context lifecycle
/// and target identity are exercised through the actual Context separately.
@MainActor
func makeFixtureModel<Module: TrainerGameModule>(
    _ module: Module.Type,
    session: TrainerBackendSession,
    logSink: TrainerLogSink,
    backendScriptURL: URL? = nil,
    makeModel: (TrainerModuleServices) -> Module.Model
) -> Module.Model {
    let services = TrainerModuleServices(
        descriptor: module.descriptor, session: session, logSink: logSink,
        targetObservation: .init(isRunning: false, launchGeneration: 0)
    )
    let model = makeModel(services)
    if let backendScriptURL {
        do {
            try session.start(
                descriptor: module.descriptor, backendScriptURL: backendScriptURL,
                applyPayload: { [weak model] in model?.applyBackendPayload($0) },
                resetGameState: { [weak model] in model?.backendDidStop() },
                log: { logSink.append($0) },
                backendLog: { logSink.append($0, source: "BACKEND") }
            )
            model.backendDidStart()
        } catch {
            // The session publishes its startup failure to the fixture model.
        }
    }
    return model
}
