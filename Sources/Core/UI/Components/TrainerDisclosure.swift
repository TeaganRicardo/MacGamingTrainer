import AppKit
import SwiftUI

/// Retain the child hierarchy and drafts while animating structural visibility.
/// Capability changes take effect immediately, independently of the layout phase.
struct TrainerDisclosure<Content: View>: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.trainerGamePageVisibility) private var pageVisibility
    @Environment(\.trainerDisclosureExpanded) private var parentExpanded
    let isExpanded: Bool
    let content: Content
    @State private var layoutExpanded: Bool
    @State private var focusAnchor = TrainerDisclosureFocusAnchor()

    init(isExpanded: Bool, @ViewBuilder content: () -> Content) {
        self.isExpanded = isExpanded
        self.content = content()
        _layoutExpanded = State(initialValue: isExpanded)
    }

    var body: some View {
        content
            .fixedSize(horizontal: false, vertical: true)
            .frame(height: layoutExpanded ? nil : 0, alignment: .top)
            .clipped()
            .opacity(layoutExpanded ? 1 : 0)
            .allowsHitTesting(isExpanded && parentExpanded)
            .disabled(!isExpanded || !parentExpanded)
            .accessibilityHidden(!isExpanded || !parentExpanded)
            .environment(\.trainerDisclosureExpanded, isExpanded && parentExpanded)
            .background(TrainerDisclosureLayoutProbe(anchor: focusAnchor)
                .allowsHitTesting(false).accessibilityHidden(true))
            .onChange(of: isExpanded) { _, expanded in
                let generation = focusAnchor.begin(visible: pageVisibility?.isVisible ?? true)
                withTransaction(TrainerMotion.transaction(.disclosure, reduceMotion: reduceMotion)) {
                    withAnimation(TrainerMotion.animation(.disclosure, reduceMotion: reduceMotion),
                                  completionCriteria: .logicallyComplete) {
                        layoutExpanded = expanded
                    } completion: {
                        focusAnchor.finish(generation)
                    }
                }
            }
            .background {
                TrainerGamePageVisibilityObserver { visible in
                    if !visible { focusAnchor.cancel() }
                }
            }
            .onDisappear { focusAnchor.cancel() }
    }
}

struct TrainerDisclosureButton: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @EnvironmentObject private var localization: TrainerLocalizationStore
    @Binding var isExpanded: Bool
    let expandTitle: String
    let collapseTitle: String

    var body: some View {
        Button { isExpanded.toggle() } label: {
            HStack(spacing: 5) {
                Text(isExpanded ? collapseTitle : expandTitle)
                Image(systemName: "chevron.down")
                    .rotationEffect(.degrees(isExpanded ? 180 : 0))
                    .animation(TrainerMotion.animation(.disclosure, reduceMotion: reduceMotion), value: isExpanded)
                    .accessibilityHidden(true)
            }
            .font(.caption.weight(.medium))
            .foregroundStyle(.secondary)
            .padding(.horizontal, 6)
            .padding(.vertical, 4)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityValue(localization.localized(isExpanded ? "host.disclosure.expanded" : "host.disclosure.collapsed"))
    }
}

/// A structural transition keeps an existing outside editor in view. This
/// short-lived anchor never grabs focus, survives only its current animation,
/// and yields immediately to pointer scrolling or another explicit click.
private final class TrainerDisclosureFocusAnchor {
    weak var probe: TrainerDisclosureLayoutProbe.Probe?
    private weak var field: NSTextField?
    private var generation: UInt = 0

    func begin(visible: Bool) -> UInt {
        generation &+= 1
        field = nil
        if visible, let probe, let editor = probe.window?.firstResponder as? NSTextView,
           editor.isFieldEditor, let candidate = editor.delegate as? NSTextField,
           candidate.enclosingScrollView === probe.enclosingScrollView {
            field = candidate
        }
        return generation
    }

    func keepVisible() {
        guard let field, field.isEnabled, field.currentEditor() != nil,
              let scroll = field.enclosingScrollView, scroll === probe?.enclosingScrollView else { return }
        let frame = field.convert(field.bounds, to: scroll.contentView)
        if !scroll.contentView.bounds.contains(frame) { _ = field.scrollToVisible(field.bounds) }
    }

    func finish(_ completed: UInt) {
        guard completed == generation else { return }
        keepVisible()
        field = nil
    }

    func cancel() { generation &+= 1; field = nil }
}

private struct TrainerDisclosureLayoutProbe: NSViewRepresentable {
    let anchor: TrainerDisclosureFocusAnchor
    final class Probe: NSView {
        weak var anchor: TrainerDisclosureFocusAnchor?
        private var monitor: Any?
        override func layout() { super.layout(); anchor?.keepVisible() }
        override func viewDidMoveToWindow() {
            super.viewDidMoveToWindow()
            stop()
            guard window != nil else { return }
            monitor = NSEvent.addLocalMonitorForEvents(matching: [.scrollWheel, .leftMouseDown]) { [weak self] event in
                guard let self, event.window === self.window, let scroll = self.enclosingScrollView,
                      scroll.bounds.contains(scroll.convert(event.locationInWindow, from: nil)) else { return event }
                self.anchor?.cancel()
                return event
            }
        }
        func stop() {
            if let monitor { NSEvent.removeMonitor(monitor) }
            monitor = nil
        }
        deinit { stop() }
    }
    func makeNSView(context: Context) -> Probe {
        let view = Probe()
        view.anchor = anchor
        anchor.probe = view
        return view
    }
    func updateNSView(_ view: Probe, context: Context) { view.needsLayout = true }
    static func dismantleNSView(_ view: Probe, coordinator: ()) { view.stop() }
}
