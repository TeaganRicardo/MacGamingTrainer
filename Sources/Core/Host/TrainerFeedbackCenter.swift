import Combine
import Foundation

/// Persistent per-context feedback center shared between Host chrome and the
/// active game model.
///
/// The center holds transient page notices, details popover presentation state,
/// backend-status error/notice transitions, and merged current issues from Core
/// and the module.
@MainActor
package final class TrainerFeedbackCenter: ObservableObject {
    @Published package private(set) var notice: TrainerFeedbackNotice?
    @Published package private(set) var detailsPresented = false
    @Published package private(set) var detailsNoticeID: UUID?

    private var backendStatus: TrainerBackendStatus
    private var issueProvider: @MainActor () -> [TrainerCurrentIssue] = { [] }
    private var issueSubscription: AnyCancellable?
    private var lastSyncedIssues: [TrainerCurrentIssue] = []
    private var suppressNextStatusNotice = false
    private var suppressNextStatusError = false
    private var suppressStatusErrorPredicate: (@MainActor (TrainerBackendStatus) -> Bool)?

    package init(initialStatus: TrainerBackendStatus = TrainerBackendStatus()) {
        self.backendStatus = initialStatus
    }

    package func setIssueProvider(_ provider: @escaping @MainActor () -> [TrainerCurrentIssue]) {
        issueSubscription = nil
        issueProvider = provider
        syncCurrentIssues()
    }

    package func setIssueProvider<Owner: ObservableObject>(
        observing owner: Owner,
        _ provider: @escaping @MainActor () -> [TrainerCurrentIssue]
    ) {
        issueProvider = provider
        issueSubscription = owner.objectWillChange
            .receive(on: DispatchQueue.main)
            .sink { [weak self] _ in
                self?.syncCurrentIssues()
            }
        syncCurrentIssues()
    }

    package func syncCurrentIssues() {
        let snapshot = currentIssues
        let changed = snapshot != lastSyncedIssues
        lastSyncedIssues = snapshot
        if detailsPresented, snapshot.isEmpty {
            detailsPresented = false
            detailsNoticeID = nil
        }
        if changed {
            objectWillChange.send()
        }
    }

    /// Merge module-owned current issues with any active backend failure unless
    /// the module already projected an issue carrying the same token.
    package var currentIssues: [TrainerCurrentIssue] {
        var issues = issueProvider()
        let backendToken = TrainerTextToken(
            key: backendStatus.error,
            arguments: backendStatus.errorArguments
        )
        if !backendToken.key.isEmpty, !issues.contains(where: { $0.text == backendToken }) {
            issues.append(TrainerCurrentIssue(id: "backend", text: backendToken))
        }
        return issues
    }

    package func present(_ text: TrainerTextToken, tone: TrainerFeedbackTone) {
        guard !text.key.isEmpty else { return }
        notice = TrainerFeedbackNotice(text: text, tone: tone)
    }

    package func present(_ key: String, arguments: [String] = [], tone: TrainerFeedbackTone) {
        present(TrainerTextToken(key: key, arguments: arguments), tone: tone)
    }

    package func dismiss(_ id: UUID) {
        guard notice?.id == id else { return }
        notice = nil
    }

    package func clearNotice() {
        notice = nil
    }

    package func showDetails(for noticeID: UUID? = nil) {
        guard !currentIssues.isEmpty else { return }
        if let noticeID, notice?.id != noticeID { return }
        detailsNoticeID = noticeID ?? notice?.id
        detailsPresented = true
    }

    package func closeDetails() {
        detailsPresented = false
        detailsNoticeID = nil
    }

    /// Suppress the trailing status notice/error from the current backend reply
    /// when a module already presented a more specific receipt or warning.
    package func suppressNextStatus(
        error: Bool = false,
        when shouldSuppressError: (@MainActor (TrainerBackendStatus) -> Bool)? = nil
    ) {
        suppressNextStatusNotice = true
        if error {
            suppressNextStatusError = true
            suppressStatusErrorPredicate = shouldSuppressError
        }
    }

    package func clearStatusSuppression() {
        suppressNextStatusNotice = false
        suppressNextStatusError = false
        suppressStatusErrorPredicate = nil
    }

    func receiveBackendStatus(previous: TrainerBackendStatus, current: TrainerBackendStatus) {
        backendStatus = current
        defer { syncCurrentIssues() }
        if current.busy { clearStatusSuppression() }

        if !current.error.isEmpty,
           current.error != previous.error || current.errorArguments != previous.errorArguments {
            let suppressed = suppressNextStatusError && (suppressStatusErrorPredicate?(current) ?? true)
            suppressNextStatusError = false
            suppressStatusErrorPredicate = nil
            if !suppressed {
                present(
                    TrainerTextToken(key: current.error, arguments: current.errorArguments),
                    tone: .warning
                )
            }
            return
        }

        if !current.notice.isEmpty, current.notice != previous.notice {
            let suppressed = suppressNextStatusNotice
            suppressNextStatusNotice = false
            if !suppressed {
                let tone: TrainerFeedbackTone = current.notice == "host.backend.notice.completed"
                    ? .success
                    : .information
                present(TrainerTextToken(key: current.notice), tone: tone)
            }
        }
    }
}
