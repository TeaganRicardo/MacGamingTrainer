"""Native shared feedback journey consumed by both game frontend fixtures."""

FEEDBACK_JOURNEY = r'''
@MainActor private final class FeedbackPresentationState: ObservableObject {
    @Published var notice: TrainerFeedbackNotice?
    @Published var detailsID: UUID?
    let pageVisibility = TrainerGamePageVisibility()
    @Published var busy = false
    @Published var connected = false
    var requests = 0
    var dismissed: [UUID] = []

    func dismiss(_ id: UUID) {
        guard notice?.id == id else { return }
        dismissed.append(id)
        notice = nil
    }
}

private struct FeedbackEditorProbe: NSViewRepresentable {
    let field: NSTextField
    func makeNSView(context: Context) -> NSTextField { field }
    func updateNSView(_ view: NSTextField, context: Context) {}
}

private struct FeedbackPresentationFixture: View {
    @ObservedObject var state: FeedbackPresentationState
    let editor: NSTextField

    var body: some View {
        VStack(spacing: 12) {
            FeedbackEditorProbe(field: editor).frame(height: 24)
            TrainerConnectionStatusCard(connected: state.connected, backendAvailable: true,
                actionsEnabled: !state.busy, onRefresh: { state.requests += 1 },
                onPrimary: { state.requests += 1; state.busy = true }, onRestart: { state.requests += 1 })
            TrainerFeedbackOverlay(notice: state.notice, onDismiss: state.dismiss,
                onDetails: { state.detailsID = $0 }, detailsNoticeID: state.detailsID)
                .environment(\.trainerGamePageVisibility, state.pageVisibility)
            Spacer(minLength: 0)
        }.padding(12)
    }
}

@MainActor
func exerciseFeedbackPresentation(localization: TrainerLocalizationStore) {
    let originalLanguage = localization.language
    defer { localization.language = originalLanguage }
    for language in [TrainerPresentationLanguage.en, .zhCN] {
        localization.language = language
        for width: CGFloat in [620, 360] {
            let state = FeedbackPresentationState()
            let editor = NSTextField(string: "focused draft")
            let host = NSHostingView(rootView: FeedbackPresentationFixture(state: state, editor: editor)
                .environmentObject(localization))
            let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: width, height: 240),
                styleMask: [.titled], backing: .buffered, defer: false)
            window.isReleasedWhenClosed = false
            window.contentView = host
            window.makeKeyAndOrderFront(nil)
            managementWait(host, "feedback draft field") { editor.window === window && editor.bounds.width > 0 }
            managementCheck(window.makeFirstResponder(editor), "feedback fixture could not focus its draft")
            let focused = window.firstResponder
            func control(_ id: String) -> NativeAccessibilityControl? {
                nativeAccessibilityControls(host).first { $0.identifier == "host.feedback." + id && $0.role == "AXButton" }
            }
            for index in 0..<12 {
                let token = TrainerTextToken(key: index.isMultiple(of: 3)
                    ? "host.backend.notice.recovered" : "host.backend.notice.completed")
                state.notice = TrainerFeedbackNotice(text: token, tone: index.isMultiple(of: 2) ? .success : .warning)
                managementWait(host, "replacement feedback remains visible") {
                    control("dismiss")?.enabled == true && managementHasText(localization.string(token), in: host)
                }
                managementCheck(window.firstResponder === focused && editor.stringValue == "focused draft",
                                "feedback replacement stole focus or replaced an unrelated draft")
                let bounds = window.convertToScreen(host.convert(host.bounds, to: nil)).insetBy(dx: -1, dy: -1)
                managementCheck(bounds.contains(control("dismiss")!.frame), "feedback controls clipped in a narrow window")
            }
            let current = state.notice!.id
            managementCheck(control("details")!.press(), "feedback details refused native AX press")
            managementWait(host, "feedback details preserve current event") { state.detailsID == current }
            managementCheck(state.notice?.id == current, "opening details dismissed its notice")
            state.detailsID = nil
            managementCheck(control("dismiss")!.press(), "feedback dismissal refused native AX press")
            managementWait(host, "feedback dismisses current event") { state.notice == nil && control("dismiss") == nil }
            managementCheck(state.dismissed == [current], "feedback dismissed an unrelated operation")

            state.notice = TrainerFeedbackNotice(text: .init(key: "host.backend.notice.completed"), tone: .information)
            managementWait(host, "feedback reappears for a later event") { control("dismiss") != nil }
            state.pageVisibility.setVisible(false)
            managementWait(host, "hidden page cannot expose feedback actions") { control("dismiss") == nil }
            managementCheck(state.notice != nil, "page selection erased its originating operation notice")
            state.pageVisibility.setVisible(true)
            managementWait(host, "returning page shows its own retained notice") { control("dismiss") != nil }
            managementCheck(state.requests == 0, "feedback transitions generated a backend action")

            managementPress(localization.localized("host.connectGame"), in: host)
            managementWait(host, "pending connection disables repeated action") {
                state.busy && namedNativeControl(host, role: "AXButton", name: localization.localized("host.connectGame"))?.enabled == false
            }
            for _ in 0..<8 {
                _ = namedNativeControl(host, role: "AXButton", name: localization.localized("host.connectGame"))?.press()
            }
            managementCheck(state.requests == 1 && !state.connected, "pending presentation fabricated success or replayed an action")
            state.connected = true; state.busy = false
            managementWait(host, "confirmed connection changes its native action") {
                namedNativeControl(host, role: "AXButton", name: localization.localized("host.disconnectGame"))?.enabled == true
            }
            managementCheck(state.requests == 1, "acknowledged connection transition sent another request")
            window.contentView = nil
            window.close()
        }
    }
    print("shared_feedback_native_presentation_ok")
}
'''
