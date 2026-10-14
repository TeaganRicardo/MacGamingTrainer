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
    @State private var hoveredNoticeID: UUID?
    @State private var focusedNoticeID: UUID?
    @FocusState private var focusedAction: Action?

    let notice: TrainerFeedbackNotice?
    let onDismiss: (UUID) -> Void
    var onDetails: ((UUID) -> Void)? = nil
    var detailsNoticeID: UUID? = nil

    private struct Schedule: Hashable {
        let noticeID: UUID?
        let paused: Bool
    }

    private enum Action: Hashable {
        case details, dismiss
    }

    private var paused: Bool {
        guard let id = notice?.id else { return false }
        return detailsNoticeID == id || hoveredNoticeID == id || focusedNoticeID == id
    }

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
                HStack(alignment: .top, spacing: 12) {
                    Label(text, systemImage: icon)
                        .font(.callout)
                        .foregroundStyle(color)
                        .lineLimit(3)
                        .fixedSize(horizontal: false, vertical: true)
                        .accessibilityLabel(text)
                        .allowsHitTesting(false)
                    HStack(spacing: 8) {
                        if let onDetails {
                            Button(localization.localized("host.feedback.details")) { onDetails(notice.id) }
                                .focused($focusedAction, equals: .details)
                        }
                        Button { onDismiss(notice.id) } label: {
                            Image(systemName: "xmark")
                        }
                        .accessibilityLabel(localization.localized("host.feedback.collapse"))
                        .help(localization.localized("host.feedback.collapse"))
                        .focused($focusedAction, equals: .dismiss)
                    }
                    .buttonStyle(.plain)
                    .font(.caption)
                    .onHover { hoveredNoticeID = $0 ? notice.id : nil }
                    .onChange(of: focusedAction) { _, focused in
                        focusedNoticeID = focused != nil ? notice.id : nil
                    }
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 10)
                .frame(maxWidth: 560)
                .background {
                    RoundedRectangle(cornerRadius: theme.controlCornerRadius)
                        .fill(theme.panelRaised).allowsHitTesting(false)
                }
                .opacity(timing.isFading ? 0 : 1)
            }
        }
        .task(id: Schedule(noticeID: notice?.id, paused: paused)) {
            guard let notice else { timing.clear(); return }
            let now = ProcessInfo.processInfo.systemUptime
            let duration = notice.tone == .warning ? TrainerFeedbackTiming.errorDuration : TrainerFeedbackTiming.ordinaryDuration
            if timing.show(notice.id, duration: duration, at: now) {
                NSAccessibility.post(
                    element: NSApplication.shared,
                    notification: .announcementRequested,
                    userInfo: [.announcement: localization.string(notice.text),
                               .priority: NSAccessibilityPriorityLevel.medium.rawValue]
                )
            }
            if paused { timing.pause(notice.id, at: now); return }
            timing.resume(notice.id, at: now)
            do {
                try await Task.sleep(for: .seconds(timing.remainingReadableTime(at: now)))
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
