import AppKit
import SwiftUI

struct TrainerGamePages: View {
    @ObservedObject var application: TrainerApplicationCoordinator
    @Environment(\.trainerTheme) private var theme
    @Environment(\.colorSchemeContrast) private var contrast
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var transition = TrainerGamePageTransition()

    var body: some View {
        HStack(spacing: 0) {
            TrainerSidebar {
                ForEach(application.contexts) { context in
                    context.makeSidebarCard(selected: context.id == application.selectedGameID) {
                        guard application.selectedGameID != context.id else { return }
                        transition.prepare(destination: context.id, reduceMotion: reduceMotion)
                        application.selectedGameID = context.id
                    }
                }
            }
            Rectangle()
                .fill(theme.boundaryColor(for: contrast))
                .frame(width: 1)
                .accessibilityHidden(true)
            ZStack(alignment: .topLeading) {
                ForEach(application.contexts) { context in
                    context.content
                        .opacity(context.id == application.selectedGameID ? 1 : 0)
                        .allowsHitTesting(context.id == application.selectedGameID)
                        .accessibilityHidden(context.id != application.selectedGameID)
                        .zIndex(context.id == application.selectedGameID ? 1 : 0)
                }
            }
        }
        .trainerSurface(.canvas)
        .background(TrainerGameSelectionFocus(gameID: application.selectedGameID, transition: transition)
            .allowsHitTesting(false).accessibilityHidden(true))
        .trainerDismissTextEditingOnClickAway()
        .disabled(application.terminationRequested)
        .onChange(of: application.selectedGameID) { _, newValue in
            transition.finish(destination: newValue)
        }
        .onChange(of: reduceMotion) { _, reduced in
            if reduced { transition.cancel() }
        }
    }
}

/// End the old page's native edit in this window only. Keep keyboard focus on
/// the sidebar selection, and never resign an independent tool window's editor.
private struct TrainerGameSelectionFocus: NSViewRepresentable {
    let gameID: String
    let transition: TrainerGamePageTransition

    final class Observer: NSView {
        var gameID: String?
        weak var transition: TrainerGamePageTransition?
        override func hitTest(_ point: NSPoint) -> NSView? { nil }
    }

    func makeNSView(context: Context) -> Observer {
        let view = Observer()
        view.transition = transition
        transition.attach(view)
        return view
    }
    func updateNSView(_ view: Observer, context: Context) {
        transition.attach(view)
        let previous = view.gameID
        view.gameID = gameID
        guard let previous, previous != gameID, let window = view.window,
              let editor = window.firstResponder as? NSTextView, editor.isFieldEditor,
              let field = editor.delegate as? NSTextField else { return }
        DispatchQueue.main.async { [weak window, weak editor, weak field] in
            guard let window, let editor, let field, window.firstResponder === editor,
                  editor.delegate as? NSTextField === field else { return }
            window.makeFirstResponder(nil)
        }
    }
    static func dismantleNSView(_ view: Observer, coordinator: ()) {
        view.transition?.detach(view)
    }
}
