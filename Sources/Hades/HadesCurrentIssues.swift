import Foundation

extension HadesTrainerModel {
    /// Current owner state only. Rejected input and stale-target refusals are
    /// one-shot feedback and never appear here.
    var currentIssues: [TrainerCurrentIssue] {
        var issues: [TrainerCurrentIssue] = []
        func append(_ id: String, _ text: TrainerTextToken?, title: TrainerTextToken? = nil) {
            guard let text, !text.key.isEmpty, !issues.contains(where: { $0.text == text }) else { return }
            issues.append(TrainerCurrentIssue(id: id, text: text, title: title))
        }
        append("catalog", catalogIssue)
        append("observation", observationIssue)
        if let speed = features[HadesFeature.gameSpeed.rawValue], let error = speed.errorPresentation {
            append("runtime.gameSpeed", TrainerTextToken(key: error, arguments: speed.errorArguments),
                   title: TrainerTextToken(key: HadesFeature.gameSpeed.key))
        }
        append("backend", TrainerTextToken(key: backendStatus.error, arguments: backendStatus.errorArguments))
        return issues
    }
}
