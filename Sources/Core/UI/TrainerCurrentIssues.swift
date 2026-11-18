import SwiftUI

/// A bounded projection of a module's current owner state, never a
/// notification history. The module decides what is current; Core presents it.
package struct TrainerCurrentIssue: Identifiable, Equatable {
    package let id: String
    package let text: TrainerTextToken
    let title: TrainerTextToken?

    package init(id: String, text: TrainerTextToken, title: TrainerTextToken? = nil) {
        self.id = id
        self.text = text
        self.title = title
    }
}

/// The operation toast of a module page. A warning offers its details while
/// the module still reports current issues; a routine notice only dismisses.
package struct TrainerOperationFeedback: View {
    let notice: TrainerFeedbackNotice?
    let hasCurrentIssues: Bool
    let detailsNoticeID: UUID?
    let onDismiss: (UUID) -> Void
    let onShowDetails: (UUID) -> Void

    package init(notice: TrainerFeedbackNotice?, hasCurrentIssues: Bool, detailsNoticeID: UUID?, onDismiss: @escaping (UUID) -> Void, onShowDetails: @escaping (UUID) -> Void) {
        self.notice = notice
        self.hasCurrentIssues = hasCurrentIssues
        self.detailsNoticeID = detailsNoticeID
        self.onDismiss = onDismiss
        self.onShowDetails = onShowDetails
    }

    package var body: some View {
        TrainerFeedbackOverlay(
            notice: notice,
            onDismiss: onDismiss,
            onDetails: notice?.tone == .warning && hasCurrentIssues ? onShowDetails : nil,
            detailsNoticeID: detailsNoticeID
        )
    }
}

/// The sidebar entry for a module's current issues. It exists only while the
/// module reports an issue; the module owns whether its details are presented,
/// and resolution or a hidden page retires that presentation.
package struct TrainerCurrentIssuesEntry: View {
    @EnvironmentObject private var localization: TrainerLocalizationStore
    let issues: [TrainerCurrentIssue]
    let detailsPresented: Bool
    let onShowDetails: () -> Void
    let onCloseDetails: () -> Void
    let onOpenLog: () -> Void

    package init(issues: [TrainerCurrentIssue], detailsPresented: Bool, onShowDetails: @escaping () -> Void, onCloseDetails: @escaping () -> Void, onOpenLog: @escaping () -> Void) {
        self.issues = issues
        self.detailsPresented = detailsPresented
        self.onShowDetails = onShowDetails
        self.onCloseDetails = onCloseDetails
        self.onOpenLog = onOpenLog
    }

    package var body: some View {
        // A transparent group takes no stack spacing while empty and still
        // observes the issues resolving.
        Group {
            if !issues.isEmpty {
                Button(action: onShowDetails) {
                    Label(localization.localized("host.feedback.currentIssues"), systemImage: TrainerSemanticIcon.Tool.currentIssues)
                        .font(.callout)
                }
                .popover(isPresented: Binding(
                    get: { detailsPresented },
                    set: { if !$0 { onCloseDetails() } }
                )) {
                    TrainerFeedbackDetails(issues: issues, onOpenLog: onOpenLog, onClose: onCloseDetails)
                }
                .background {
                    TrainerGamePageVisibilityObserver { visible in
                        if !visible { onCloseDetails() }
                    }
                }
            }
        }
        .onChange(of: issues) { _, issues in
            if issues.isEmpty { onCloseDetails() }
        }
    }
}

struct TrainerFeedbackDetails: View {
    @Environment(\.trainerTheme) private var theme
    @EnvironmentObject private var localization: TrainerLocalizationStore
    let issues: [TrainerCurrentIssue]
    let onOpenLog: () -> Void
    let onClose: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: theme.sheetSpacing) {
            Text(localization.localized("host.feedback.currentIssues")).font(.headline)
            ScrollView {
                VStack(alignment: .leading, spacing: theme.sheetSpacing) {
                    ForEach(issues) { issue in
                        VStack(alignment: .leading, spacing: 4) {
                            if let title = issue.title { Text(localization.string(title)).font(.subheadline.weight(.medium)) }
                            Text(localization.string(issue.text))
                                .fixedSize(horizontal: false, vertical: true)
                                .textSelection(.enabled)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                    }
                }
            }
            .frame(maxHeight: 320)
            HStack {
                Button(localization.localized("host.viewLog"), action: onOpenLog)
                Spacer()
                Button(localization.localized("host.feedback.closeDetails"), action: onClose)
                     .keyboardShortcut(.defaultAction)
            }
        }
        .padding(theme.panelPadding)
        .frame(width: theme.popoverDetailsWidth)
        .trainerSurface(.canvas)
        .onExitCommand(perform: onClose)
    }
}
