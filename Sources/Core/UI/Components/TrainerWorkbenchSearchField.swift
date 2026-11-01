import SwiftUI

/// Shared discovery presentation. Entries, names, icons and reveal/navigation
/// semantics stay with the module; this view does not receive a backend session.
struct TrainerWorkbenchSearchField<Entry: Identifiable>: View {
    @State private var pageVisible = true
    @Environment(\.trainerTheme) private var theme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Binding var text: String
    let placeholder: String
    let clearLabel: String
    let emptyLabel: String
    let search: (String) -> [Entry]
    let title: (Entry) -> String
    let detail: (Entry) -> String
    let icon: (Entry) -> String
    let onNavigate: (Entry) -> Void
    @State private var presentation = TrainerWorkbenchSearchPresentation<Entry.ID>()
    @State private var fieldWidth: CGFloat = 420
    @FocusState private var searchFocused: Bool

    private var results: [Entry] { search(text) }

    private func locate(_ entry: Entry) {
        if presentation.select(entry.id, query: text, pageVisible: pageVisible,
                               search: search, identifier: { $0.id }, navigate: onNavigate) {
            searchFocused = false
        }
    }

    private func submitSearch() {
        if presentation.submit(query: text, pageVisible: pageVisible, search: search,
                               identifier: { $0.id }, navigate: onNavigate) {
            searchFocused = false
        } else if text.isEmpty && pageVisible {
            searchFocused = true
        }
    }

    private func moveSelection(by offset: Int) -> Bool {
        presentation.moveSelection(by: offset, query: text, pageVisible: pageVisible, results: results.map(\.id))
    }

    private func dismissResults() {
        presentation.dismiss()
        if pageVisible { searchFocused = true }
    }

    var body: some View {
        TrainerSearchField(
            text: $text, placeholder: placeholder, clearLabel: clearLabel,
            focus: $searchFocused, onSubmit: submitSearch, onMoveSelection: moveSelection
        )
        .disabled(!pageVisible)
        .background {
            GeometryReader { proxy in
                Color.clear.onChange(of: proxy.size.width, initial: true) { _, width in fieldWidth = width }
            }
        }
        .popover(isPresented: $presentation.resultsPresented, arrowEdge: .bottom) {
            let entries = results
            ScrollViewReader { scroll in
                ZStack {
                    ScrollView {
                        VStack(spacing: 0) {
                            ForEach(entries) { entry in
                                TrainerSectionButton(
                                    title: title(entry), detail: detail(entry), systemImage: icon(entry)
                                ) { locate(entry) }
                                // The query owns Arrow/Return selection. A
                                // result remains a native mouse/AX action,
                                // without taking the active text editor's focus.
                                .focusable(false)
                                .padding(.horizontal, 8)
                                .background {
                                    RoundedRectangle(cornerRadius: 6)
                                        .fill(theme.accent.opacity(presentation.selectedID == entry.id ? 0.14 : 0))
                                        .animation(TrainerMotion.animation(.selection, reduceMotion: reduceMotion),
                                                   value: presentation.selectedID)
                                }
                                .accessibilityAddTraits(presentation.selectedID == entry.id ? .isSelected : [])
                                .accessibilityIdentifier("trainer.workbench.result.\(entry.id)")
                                .id(entry.id)
                            }
                        }
                    }
                    .opacity(entries.isEmpty ? 0 : 1)
                    .allowsHitTesting(!entries.isEmpty)
                    .accessibilityHidden(entries.isEmpty)
                    TrainerEmptyState(text: emptyLabel)
                        .opacity(entries.isEmpty ? 1 : 0)
                        .allowsHitTesting(false)
                        .accessibilityHidden(!entries.isEmpty)
                }
                // Keep the same native popover and scroll viewport while the
                // query changes. Only selection/empty feedback animates.
                .frame(height: 312)
                .animation(TrainerMotion.animation(.transientFeedback, reduceMotion: reduceMotion),
                           value: entries.isEmpty)
                .onChange(of: presentation.selectedID) { _, id in
                    if let id { scroll.scrollTo(id) }
                }
            }
            .padding(8)
            // Budget the entire content, including its padding. AppKit owns
            // the native popover's additional arrow and window decoration.
            .frame(width: max(180, min(fieldWidth, 420)))
            .onMoveCommand { direction in
                if direction == .up { _ = moveSelection(by: -1) }
                if direction == .down { _ = moveSelection(by: 1) }
            }
            .onExitCommand(perform: dismissResults)
        }
        .onChange(of: text) { _, query in
            presentation.queryChanged(query, pageVisible: pageVisible, results: results.map(\.id))
        }
        .onChange(of: results.map(\.id)) { _, ids in
            presentation.resultsChanged(ids)
        }
        .background {
            TrainerGamePageVisibilityObserver { visible in
                pageVisible = visible
                presentation.pageVisibilityChanged(visible)
                if !visible { searchFocused = false }
            }
        }
        .onExitCommand(perform: dismissResults)
        .onDisappear {
            presentation.dismiss()
            searchFocused = false
        }
    }
}
