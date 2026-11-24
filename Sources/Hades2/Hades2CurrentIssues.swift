import Foundation
import TrainerCore

extension Hades2TrainerModel {
    var hostCurrentIssues: [TrainerCurrentIssue] {
        var issues: [TrainerCurrentIssue] = []
        func append(_ id: String, _ text: TrainerTextToken, title: TrainerTextToken? = nil) {
            guard !text.key.isEmpty else { return }
            issues.append(TrainerCurrentIssue(id: id, text: text, title: title))
        }
        if let result = receivedActionResultText { append("result", result) }
        append("operation", errorText)
        if let local = localErrorToken, local != errorText { append("local", local) }
        if !runtimeIssuePresentations.isEmpty {
            for issue in runtimeIssuePresentations {
                let title = issue.featureID == "gameSpeed"
                    ? TrainerTextToken(key: "hades2.gameSpeed.title")
                    : ShortcutAction(rawValue: issue.featureID).map { TrainerTextToken(key: $0.presentationKey) }
                append("runtime.\(issue.featureID)", issue.token, title: title)
            }
        } else {
            append("runtime", TrainerTextToken(key: runtimeIssue))
        }
        let warningLines = warning.split(separator: "\n", omittingEmptySubsequences: true).map(String.init)
        if warningLines.count <= 1 {
            append("warning", TrainerTextToken(key: warning))
        } else {
            for (index, line) in warningLines.enumerated() {
                append(index == 0 ? "warning" : "warning.\(index)", TrainerTextToken(key: line))
            }
        }
        if status == "incompatible" {
            append("compatibility", TrainerTextToken(key: "hades2.status.unverifiedBanner"))
        } else if status == "restart_required" {
            append("recovery", statusTitle)
        }
        return issues
    }
}
