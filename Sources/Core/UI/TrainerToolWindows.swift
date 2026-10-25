import AppKit
import SwiftUI

/// A tool supplies its own content and close policy. The Host owns the native
/// window; modules keep document/session meaning inside their content owner.
struct TrainerToolWindowContent {
    let view: AnyView
    let canClose: () -> Bool
    let onClose: () -> Void

    init<Content: View>(canClose: @escaping () -> Bool = { true },
                        onClose: @escaping () -> Void = {},
                        @ViewBuilder content: () -> Content) {
        view = AnyView(content())
        self.canClose = canClose
        self.onClose = onClose
    }
}

struct TrainerToolWindowActions {
    let open: (String, String, () -> TrainerToolWindowContent) -> Void
    static let none = TrainerToolWindowActions(open: { _, _, _ in })
}

private struct TrainerToolWindowActionsKey: EnvironmentKey {
    static let defaultValue = TrainerToolWindowActions.none
}

private struct TrainerCloseToolWindowKey: EnvironmentKey {
    static let defaultValue: (() -> Void)? = nil
}

extension EnvironmentValues {
    var trainerToolWindows: TrainerToolWindowActions {
        get { self[TrainerToolWindowActionsKey.self] }
        set { self[TrainerToolWindowActionsKey.self] = newValue }
    }

    var trainerCloseToolWindow: (() -> Void)? {
        get { self[TrainerCloseToolWindowKey.self] }
        set { self[TrainerCloseToolWindowKey.self] = newValue }
    }
}

@MainActor
final class TrainerToolWindowStore: NSObject, ObservableObject, NSWindowDelegate {
    private struct Entry {
        let window: NSWindow
        let content: TrainerToolWindowContent
    }
    private var entries: [String: Entry] = [:]

    var canCloseAll: Bool { entries.values.allSatisfy { $0.content.canClose() } }

    func closeAll() {
        for entry in Array(entries.values) { entry.window.performClose(nil) }
    }

    func actions(localization: TrainerLocalizationStore, theme: TrainerTheme) -> TrainerToolWindowActions {
        TrainerToolWindowActions { [weak self] id, title, content in
            self?.open(id: id, title: title, localization: localization, theme: theme, content: content)
        }
    }

    /// Reuse the existing view/model before invoking the factory. Opening the
    /// same entry again must not re-read a document or replace its drafts.
    @discardableResult
    func open(id: String, title: String, localization: TrainerLocalizationStore, theme: TrainerTheme,
              content: () -> TrainerToolWindowContent) -> NSWindow {
        if let entry = entries[id] {
            entry.window.title = title
            entry.window.makeKeyAndOrderFront(nil)
            return entry.window
        }
        let content = content()
        let window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 800, height: 700),
            styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false
        )
        window.isReleasedWhenClosed = false
        window.title = title
        window.delegate = self
        let root = content.view
            .environmentObject(localization)
            .trainerTheme(theme)
            .tint(theme.accent)
            .preferredColorScheme(.dark)
            .environment(\.trainerToolWindows, actions(localization: localization, theme: theme))
            .environment(\.trainerCloseToolWindow, { [weak window] in window?.performClose(nil) })
        let controller = NSHostingController(rootView: root)
        controller.sizingOptions = [.minSize]
        window.contentViewController = controller
        window.setContentSize(controller.view.fittingSize)
        window.center()
        entries[id] = Entry(window: window, content: content)
        window.makeKeyAndOrderFront(nil)
        return window
    }

    func windowShouldClose(_ sender: NSWindow) -> Bool {
        entries.values.first(where: { $0.window === sender })?.content.canClose() ?? true
    }

    func windowWillClose(_ notification: Notification) {
        guard let window = notification.object as? NSWindow,
              let id = entries.first(where: { $0.value.window === window })?.key,
              let entry = entries.removeValue(forKey: id) else { return }
        entry.content.onClose()
    }
}
