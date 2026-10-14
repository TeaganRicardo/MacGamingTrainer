import SwiftUI

struct Hades2FeedbackDetails: View {
    @ObservedObject var model: Hades2TrainerModel
    @Environment(\.trainerTheme) private var theme
    @EnvironmentObject private var localization: TrainerLocalizationStore

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text(localization.localized("host.feedback.currentIssues")).font(.headline)
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    ForEach(model.currentIssues) { issue in
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
                Button(localization.localized("host.viewLog")) { model.openLog() }
                Spacer()
                Button(localization.localized("host.feedback.closeDetails")) { model.closeFeedbackDetails() }
            }
        }
        .padding(20)
        .frame(width: 360)
        .background(theme.background)
    }
}
