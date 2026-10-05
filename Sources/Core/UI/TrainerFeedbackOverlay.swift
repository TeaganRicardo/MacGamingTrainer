import AppKit
import SwiftUI

enum TrainerFeedbackTone {
    case information, success, warning
}

/// An ephemeral presentation event, separate from authoritative operation and
/// recovery state. Equal text from a new operation receives a new identity.
struct TrainerFeedbackNotice: Identifiable {
    let id = UUID()
    let text: TrainerTextToken
    let tone: TrainerFeedbackTone
}

struct TrainerFeedbackOverlay: View {
    @Environment(\.trainerTheme) private var theme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @EnvironmentObject private var localization: TrainerLocalizationStore
    @State private var timing = TrainerFeedbackTiming()

    let notice: TrainerFeedbackNotice?
    let onDismiss: (UUID) -> Void

    private var color: Color {
        switch notice?.tone {
        case .success: return theme.success
        case .warning: return theme.warning
        default: return theme.info
        }
    }

    private var icon: String {
        switch notice?.tone {
        case .success: return "checkmark.circle.fill"
        case .warning: return "exclamationmark.triangle.fill"
        default: return "info.circle.fill"
        }
    }

    var body: some View {
        ZStack {
            if let notice, timing.currentID == notice.id {
                let text = localization.string(notice.text)
                Label(text, systemImage: icon)
                    .font(.callout)
                    .foregroundStyle(color)
                    .lineLimit(2)
                    .padding(.horizontal, 16)
                    .padding(.vertical, 10)
                    .frame(maxWidth: 680)
                    .background(theme.panelRaised, in: RoundedRectangle(cornerRadius: theme.controlCornerRadius))
                    .accessibilityElement(children: .ignore)
                    .accessibilityLabel(text)
                    .opacity(timing.isFading ? 0 : 1)
            }
        }
        .frame(maxWidth: .infinity)
        .frame(height: 72)
        .padding(.horizontal, 16)
        .allowsHitTesting(false)
        .task(id: notice?.id) {
            guard let notice else { timing.clear(); return }
            let now = ProcessInfo.processInfo.systemUptime
            if timing.show(notice.id, at: now) {
                NSAccessibility.post(
                    element: NSApplication.shared,
                    notification: .announcementRequested,
                    userInfo: [.announcement: localization.string(notice.text),
                               .priority: NSAccessibilityPriorityLevel.medium.rawValue]
                )
            }
            do {
                try await Task.sleep(for: .seconds(TrainerFeedbackTiming.readableDuration))
                guard !Task.isCancelled else { return }
                withAnimation(reduceMotion ? nil : .easeOut(duration: TrainerFeedbackTiming.fadeDuration)) {
                    timing.advance(notice.id, at: ProcessInfo.processInfo.systemUptime)
                }
                try await Task.sleep(for: .seconds(TrainerFeedbackTiming.fadeDuration))
                guard !Task.isCancelled else { return }
                timing.advance(notice.id, at: ProcessInfo.processInfo.systemUptime)
                if timing.currentID == nil { onDismiss(notice.id) }
            } catch {
                // A newer event cancels this task. Its identity also guards the
                // pure timing state and the module's dismissal boundary.
            }
        }
    }
}
