import AppKit
import SwiftUI

/// Standard modal/sheet chrome shared by game modules. Width is intentionally a
/// content decision; title typography, outer padding and vertical rhythm are not.
struct TrainerSheetScaffold<HeaderActions: View, Content: View, Footer: View>: View {
    @Environment(\.trainerTheme) private var theme
    let title: String
    let icon: String?
    let width: CGFloat
    let minimumWidth: CGFloat
    let headerActions: HeaderActions
    let content: Content
    let footer: Footer

    init(
        title: String,
        icon: String? = nil,
        width: CGFloat,
        minimumWidth: CGFloat? = nil,
        @ViewBuilder headerActions: () -> HeaderActions,
        @ViewBuilder content: () -> Content,
        @ViewBuilder footer: () -> Footer
    ) {
        self.title = title
        self.icon = icon
        self.width = width
        self.minimumWidth = min(minimumWidth ?? width, width)
        self.headerActions = headerActions()
        self.content = content()
        self.footer = footer()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: theme.sheetSpacing) {
            TrainerSheetHeaderLayout(spacing: theme.compactControlSpacing) {
                if let icon {
                    Label(title, systemImage: icon).font(.title2.bold())
                } else {
                    Text(title).font(.title2.bold())
                }
                headerActions
            }
            content
            footer
        }
        .padding(theme.sheetPadding)
        .frame(minWidth: minimumWidth, idealWidth: width, maxWidth: width)
        .background(theme.background.ignoresSafeArea())
    }
}

/// Reflow the existing header controls without switching view branches. Their
/// native focus and identity survive a narrow sheet or a longer translation.
private struct TrainerSheetHeaderLayout: Layout {
    let spacing: CGFloat

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        arrangement(width: proposal.width, subviews: subviews).size
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let frames = arrangement(width: bounds.width, subviews: subviews).frames
        for (view, frame) in zip(subviews, frames) {
            view.place(at: CGPoint(x: bounds.minX + frame.minX, y: bounds.minY + frame.minY),
                       anchor: .topLeading, proposal: .init(width: frame.width, height: frame.height))
        }
    }

    private func arrangement(width: CGFloat?, subviews: Subviews) -> (size: CGSize, frames: [CGRect]) {
        guard !subviews.isEmpty else { return (.zero, []) }
        var sizes = subviews.map { $0.sizeThatFits(.unspecified) }
        let naturalWidth = sizes.reduce(0) { $0 + $1.width } + spacing * CGFloat(sizes.count - 1)
        let available = max(0, width.flatMap { $0.isFinite ? $0 : nil } ?? naturalWidth)
        for index in sizes.indices where sizes[index].width > available {
            sizes[index] = subviews[index].sizeThatFits(.init(width: available, height: nil))
        }
        let rowWidth = sizes.reduce(0) { $0 + $1.width } + spacing * CGFloat(sizes.count - 1)
        if rowWidth <= available {
            let height = sizes.map(\.height).max() ?? 0
            var frames = [CGRect(x: 0, y: (height - sizes[0].height) / 2, width: sizes[0].width, height: sizes[0].height)]
            let actions = sizes.dropFirst()
            var x = available - actions.reduce(0) { $0 + $1.width } - spacing * CGFloat(max(actions.count - 1, 0))
            for size in actions {
                frames.append(CGRect(x: x, y: (height - size.height) / 2, width: size.width, height: size.height))
                x += size.width + spacing
            }
            return (CGSize(width: available, height: height), frames)
        }
        var frames = [CGRect(origin: .zero, size: sizes[0])]
        var x: CGFloat = 0
        var y = sizes[0].height + spacing
        var rowHeight: CGFloat = 0
        for size in sizes.dropFirst() {
            if x > 0 && x + size.width > available {
                x = 0
                y += rowHeight + spacing
                rowHeight = 0
            }
            frames.append(CGRect(x: x, y: y, width: size.width, height: size.height))
            x += size.width + spacing
            rowHeight = max(rowHeight, size.height)
        }
        return (CGSize(width: available, height: y + rowHeight), frames)
    }
}

/// Shared completion gesture owner for modal sheets and transient tool panels.
/// The footer's Done button and these entry points must call the same callback.
/// The native editor gets the first opportunity to finish an IME composition;
/// multiline NSTextView uses Shift-Return for newline; marked text remains native.
extension View {
    func trainerSheetDoneGestures(
        enabled: Bool = true,
        outsideWindowClicks: Bool = false,
        perform action: @escaping () -> Void
    ) -> some View {
        background(
            TrainerSheetDoneMonitor(enabled: enabled, outsideWindowClicks: outsideWindowClicks, action: action)
                .allowsHitTesting(false)
                .accessibilityHidden(true)
        )
    }

}

private struct TrainerSheetDoneMonitor: NSViewRepresentable {
    let enabled: Bool
    let outsideWindowClicks: Bool
    let action: () -> Void

    final class HostView: NSView {
        var enabled = true
        var outsideWindowClicks = false
        var action: (() -> Void)?
        private var monitor: Any?

        override func viewDidMoveToWindow() {
            super.viewDidMoveToWindow()
            stop()
            guard window != nil else { return }
            monitor = NSEvent.addLocalMonitorForEvents(
                matching: [.keyDown, .leftMouseDown, .rightMouseDown, .otherMouseDown]
            ) { [weak self] event in
                guard let self, self.enabled, let window = self.window,
                      window.isVisible, window.attachedSheet == nil else { return event }

                if event.type == .keyDown {
                    guard event.window === window, !event.isARepeat,
                          [36, 53, 76].contains(Int(event.keyCode)),
                          event.modifierFlags.intersection([.command, .option, .control, .shift, .function]).isEmpty
                    else { return event }
                    return self.finish(event, in: window)
                }

                guard let clickedWindow = event.window, clickedWindow !== window else { return event }
                let parentSheetClick = window.sheetParent.map { $0 === clickedWindow } ?? false
                let otherToolWindowClick = self.outsideWindowClicks && window.sheetParent == nil
                    && window.isKeyWindow && clickedWindow.styleMask.contains(.titled)
                    && clickedWindow.level == .normal
                guard parentSheetClick || otherToolWindowClick else { return event }
                return self.finish(event, in: window)
            }
        }

        private func finish(_ event: NSEvent, in window: NSWindow) -> NSEvent? {
            if let editor = window.firstResponder as? NSTextView {
                if editor.hasMarkedText() { return event }
                if !editor.isFieldEditor {
                    // Both keys and outside clicks are Done. Shift-Return is
                    // still available for a newline in a multiline JSON draft.
                    action?()
                    return nil
                }
                // Commit ordinary TextField editing before invoking Done. A
                // rejecting field editor keeps its sheet and draft intact.
                guard window.makeFirstResponder(nil) else { return event }
                DispatchQueue.main.async { [weak self, weak window] in
                    guard let self, self.enabled, let window,
                          self.window === window, window.attachedSheet == nil else { return }
                    self.action?()
                }
            } else {
                action?()
            }
            // A click on the blocked parent must never also activate its controls.
            return nil
        }

        func stop() {
            if let monitor { NSEvent.removeMonitor(monitor) }
            monitor = nil
        }

        deinit { stop() }
    }

    func makeNSView(context: Context) -> HostView {
        let view = HostView()
        view.enabled = enabled
        view.outsideWindowClicks = outsideWindowClicks
        view.action = action
        return view
    }

    func updateNSView(_ view: HostView, context: Context) {
        view.enabled = enabled
        view.outsideWindowClicks = outsideWindowClicks
        view.action = action
    }

    static func dismantleNSView(_ view: HostView, coordinator: ()) {
        view.stop()
    }
}
