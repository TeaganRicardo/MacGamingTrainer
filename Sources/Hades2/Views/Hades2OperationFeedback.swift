import SwiftUI

struct Hades2OperationFeedback: View {
    @ObservedObject var model: Hades2TrainerModel

    var body: some View {
        TrainerOperationFeedback(
            notice: model.feedbackNotice,
            hasCurrentIssues: !model.currentIssues.isEmpty,
            detailsNoticeID: model.feedbackDetailsNoticeID,
            onDismiss: model.dismissFeedback,
            onShowDetails: { model.showFeedbackDetails(for: $0) }
        )
    }
}
