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
    @State private var pageVisible = true
    @EnvironmentObject private var localization: TrainerLocalizationStore
    @State private var timing = TrainerFeedbackTiming()
    @State private var hovered = false
    @State private var interactiveNoticeID: UUID?
    @FocusState private var focusedAction: Action?

    let notice: TrainerFeedbackNotice?
    let onDismiss: (UUID) -> Void
    var onDetails: ((UUID) -> Void)? = nil
    var detailsNoticeID: UUID? = nil

    private struct Schedule: Hashable {
        let noticeID: UUID?
        let paused: Bool
        let visible: Bool
    }

    private enum Action: Hashable {
        case details, dismiss
    }

    private var paused: Bool {
        guard let id = notice?.id else { return false }
        return detailsNoticeID == id || hovered || focusedAction != nil
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
            if pageVisible, let notice {
                let text = localization.string(notice.text)
                HStack(alignment: .top, spacing: 12) {
                    Label(text, systemImage: icon)
                        .font(.callout)
                        .foregroundStyle(color)
                        .lineLimit(3)
                        .fixedSize(horizontal: false, vertical: true)
                        .accessibilityLabel(text)
                        .allowsHitTesting(false)
                        .contentTransition(.opacity)
                        .animation(TrainerMotion.animation(.transientFeedback, reduceMotion: reduceMotion),
                                   value: notice.text)
                    HStack(spacing: 8) {
                        if let onDetails {
                            Button(localization.localized("host.feedback.details")) {
                                guard interactiveNoticeID == notice.id else { return }
                                onDetails(notice.id)
                            }
                                .focused($focusedAction, equals: .details)
                                .accessibilityIdentifier("host.feedback.details")
                        }
                        Button {
                            guard interactiveNoticeID == notice.id else { return }
                            onDismiss(notice.id)
                        } label: {
                            Image(systemName: "xmark")
                        }
                        .accessibilityLabel(localization.localized("host.feedback.collapse"))
                        .help(localization.localized("host.feedback.collapse"))
                        .focused($focusedAction, equals: .dismiss)
                        .accessibilityIdentifier("host.feedback.dismiss")
                    }
                    .buttonStyle(.plain)
                    .font(.caption)
                    .transaction { TrainerMotion.nativeControlTransaction(&$0, reduceMotion: reduceMotion) }
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 10)
                .frame(maxWidth: 560)
                .background {
                    RoundedRectangle(cornerRadius: theme.controlCornerRadius)
                        .fill(theme.panelRaised).allowsHitTesting(false)
                }
                // The timer is asynchronous. A replacement is immediately
                // visible, while retaining the same controls and their focus.
                .opacity(timing.currentID == notice.id && timing.isFading ? 0 : 1)
                .animation(TrainerMotion.animation(.transientFeedback, reduceMotion: reduceMotion),
                           value: timing.currentID == notice.id && timing.isFading)
                .onHover { hovered = $0 }
                .onExitCommand {
                    guard interactiveNoticeID == notice.id else { return }
                    onDismiss(notice.id)
                }
                .transition(.opacity)
            }
        }
        .animation(TrainerMotion.animation(.transientFeedback, reduceMotion: reduceMotion), value: notice != nil)
        .transaction { TrainerMotion.nativeControlTransaction(&$0, reduceMotion: reduceMotion) }
        .background {
            TrainerGamePageVisibilityObserver { visible in
                pageVisible = visible
                if !visible { focusedAction = nil; hovered = false }
            }
        }
        .onChange(of: Schedule(noticeID: notice?.id, paused: false, visible: pageVisible), initial: true) { _, schedule in
            interactiveNoticeID = schedule.visible ? schedule.noticeID : nil
        }
        .onDisappear { interactiveNoticeID = nil }
        .task(id: Schedule(noticeID: notice?.id, paused: paused, visible: pageVisible)) {
            let now = ProcessInfo.processInfo.systemUptime
            let duration = notice?.tone == .warning ? TrainerFeedbackTiming.errorDuration : TrainerFeedbackTiming.ordinaryDuration
            let announce = timing.synchronize(noticeID: notice?.id, duration: duration,
                                              visible: pageVisible, paused: paused, at: now)
            guard pageVisible, let notice else { return }
            if announce {
                NSAccessibility.post(
                    element: NSApplication.shared,
                    notification: .announcementRequested,
                    userInfo: [.announcement: localization.string(notice.text),
                               .priority: NSAccessibilityPriorityLevel.medium.rawValue]
                )
            }
            guard !paused else { return }
            do {
                try await Task.sleep(for: .seconds(timing.remainingReadableTime(at: now)))
                guard !Task.isCancelled else { return }
                timing.advance(notice.id, at: ProcessInfo.processInfo.systemUptime)
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
