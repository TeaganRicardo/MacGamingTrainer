import SwiftUI

package struct TrainerSaveEditorDocumentOption: Identifiable, Equatable {
    package let id: String
    package let title: String

    package init(id: String, title: String) {
        self.id = id
        self.title = title
    }
}

package struct TrainerSaveEditorWindowHeader: View {
    @Environment(\.trainerTheme) private var theme

    let title: String
    var subtitle: String? = nil
    let busy: Bool
    let refreshTitle: String?
    let refreshEnabled: Bool
    let doneTitle: String
    let doneEnabled: Bool
    let onRefresh: (() -> Void)?
    let onDone: () -> Void

    package init(title: String, subtitle: String? = nil, busy: Bool, refreshTitle: String?, refreshEnabled: Bool, doneTitle: String, doneEnabled: Bool, onRefresh: (() -> Void)?, onDone: @escaping () -> Void) {
        self.title = title
        self.subtitle = subtitle
        self.busy = busy
        self.refreshTitle = refreshTitle
        self.refreshEnabled = refreshEnabled
        self.doneTitle = doneTitle
        self.doneEnabled = doneEnabled
        self.onRefresh = onRefresh
        self.onDone = onDone
    }

    package var body: some View {
        HStack(spacing: theme.sectionSpacing) {
            Image(systemName: TrainerSemanticIcon.Tool.saveEditor)
                .font(.title3)
                .foregroundStyle(theme.accent)
            Text(title)
                .font(.title3.weight(.semibold))
            if let subtitle, !subtitle.isEmpty {
                Text(subtitle)
                    .font(.callout)
                    .foregroundStyle(.secondary)
            } else if busy {
                TrainerLoadingIndicator()
            }
            Spacer()
            if let refreshTitle, let onRefresh {
                Button(action: onRefresh) {
                    Image(systemName: TrainerSemanticIcon.Concept.refresh)
                }
                .buttonStyle(.borderless)
                .disabled(!refreshEnabled)
                .help(refreshTitle)
                .accessibilityLabel(refreshTitle)
            }
            Button(doneTitle, action: onDone)
                .disabled(!doneEnabled)
        }
        .padding(.horizontal, theme.rowHorizontalPadding)
        .padding(.vertical, theme.sectionSpacing)
    }
}

package struct TrainerSaveEditorDocumentBar: View {
    @Environment(\.trainerTheme) private var theme

    let sourceLabel: String
    let sourcePlaceholder: String
    @Binding var sourceSelection: String
    let sources: [TrainerSaveEditorDocumentOption]
    let sourceEnabled: Bool
    let sourceRefreshTitle: String
    let onRefreshSources: () -> Void

    let targetLabel: String
    let targetPlaceholder: String
    @Binding var targetSelection: String
    let targets: [TrainerSaveEditorDocumentOption]
    let targetEnabled: Bool

    package init(sourceLabel: String, sourcePlaceholder: String, sourceSelection: Binding<String>, sources: [TrainerSaveEditorDocumentOption], sourceEnabled: Bool, sourceRefreshTitle: String, onRefreshSources: @escaping () -> Void, targetLabel: String, targetPlaceholder: String, targetSelection: Binding<String>, targets: [TrainerSaveEditorDocumentOption], targetEnabled: Bool) {
        self.sourceLabel = sourceLabel
        self.sourcePlaceholder = sourcePlaceholder
        self._sourceSelection = sourceSelection
        self.sources = sources
        self.sourceEnabled = sourceEnabled
        self.sourceRefreshTitle = sourceRefreshTitle
        self.onRefreshSources = onRefreshSources
        self.targetLabel = targetLabel
        self.targetPlaceholder = targetPlaceholder
        self._targetSelection = targetSelection
        self.targets = targets
        self.targetEnabled = targetEnabled
    }

    package var body: some View {
        HStack(spacing: theme.sectionSpacing) {
            Text(sourceLabel)
                .font(.caption)
                .foregroundStyle(.secondary)
            Picker(sourceLabel, selection: $sourceSelection) {
                Text(sourcePlaceholder).tag("")
                ForEach(sources) { option in
                    Text(option.title).tag(option.id)
                }
            }
            .labelsHidden()
            .trainerPicker(.form, state: sourceEnabled ? .interactive : .unavailable)

            Button(action: onRefreshSources) {
                Image(systemName: TrainerSemanticIcon.Concept.refresh)
            }
            .buttonStyle(.borderless)
            .disabled(!sourceEnabled)
            .help(sourceRefreshTitle)
            .accessibilityLabel(sourceRefreshTitle)

            Divider().frame(height: 20)

            Text(targetLabel)
                .font(.caption)
                .foregroundStyle(.secondary)
            Picker(targetLabel, selection: $targetSelection) {
                Text(targetPlaceholder).tag("")
                ForEach(targets) { option in
                    Text(option.title).tag(option.id)
                }
            }
            .labelsHidden()
            .trainerPicker(.form, state: targetEnabled ? .interactive : .unavailable)

            Spacer(minLength: 0)
        }
        .padding(.horizontal, theme.rowHorizontalPadding)
        .padding(.vertical, theme.inlineRowVerticalPadding)
    }
}

package struct TrainerSaveEditorWorkbenchBar<Scope: View, Trailing: View>: View {
    @Environment(\.trainerTheme) private var theme

    @Binding var search: String
    let searchPlaceholder: String
    let clearLabel: String
    let searchEnabled: Bool
    let loading: Bool
    let onSubmit: () -> Void
    let scope: Scope
    let trailing: Trailing

    package init(
        search: Binding<String>,
        searchPlaceholder: String,
        clearLabel: String,
        searchEnabled: Bool,
        loading: Bool,
        onSubmit: @escaping () -> Void,
        @ViewBuilder scope: () -> Scope,
        @ViewBuilder trailing: () -> Trailing
    ) {
        _search = search
        self.searchPlaceholder = searchPlaceholder
        self.clearLabel = clearLabel
        self.searchEnabled = searchEnabled
        self.loading = loading
        self.onSubmit = onSubmit
        self.scope = scope()
        self.trailing = trailing()
    }

    package var body: some View {
        HStack(spacing: theme.sectionSpacing) {
            TrainerSearchField(
                text: $search,
                placeholder: searchPlaceholder,
                clearLabel: clearLabel,
                onSubmit: onSubmit
            )
            .disabled(!searchEnabled)

            if loading {
                TrainerLoadingIndicator()
            }

            scope
            trailing
        }
        .padding(.horizontal, theme.rowHorizontalPadding)
        .padding(.vertical, theme.sectionSpacing)
    }
}

package struct TrainerSaveEditorWorkspace<Results: View, Paging: View, Review: View>: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.trainerTheme) private var theme

    let identity: AnyHashable?
    let hasReview: Bool
    let busy: Bool
    let showsPaging: Bool
    let results: Results
    let paging: Paging
    let review: Review

    package init(
        identity: AnyHashable?,
        hasReview: Bool,
        busy: Bool,
        showsPaging: Bool,
        @ViewBuilder results: () -> Results,
        @ViewBuilder paging: () -> Paging,
        @ViewBuilder review: () -> Review
    ) {
        self.identity = identity
        self.hasReview = hasReview
        self.busy = busy
        self.showsPaging = showsPaging
        self.results = results()
        self.paging = paging()
        self.review = review()
    }

    package var body: some View {
        VStack(spacing: 0) {
            results
                .id(identity)
                .frame(minHeight: 300, idealHeight: hasReview ? 445 : 610, maxHeight: .infinity)

            if showsPaging {
                Divider()
                paging
                    .padding(.horizontal, theme.rowHorizontalPadding)
                    .padding(.vertical, theme.inlineRowVerticalPadding)
            }

            VStack(spacing: 0) {
                if hasReview {
                    Divider()
                    review
                        .frame(height: 240)
                        .transition(.opacity)
                }
            }
            .frame(height: hasReview ? 241 : 0, alignment: .top)
            .clipped()
            .allowsHitTesting(hasReview && !busy)
            .accessibilityHidden(!hasReview)
        }
        .animation(TrainerMotion.animation(.disclosure, reduceMotion: reduceMotion), value: hasReview)
    }
}

package struct TrainerSaveEditorPagingBar: View {
    @Environment(\.trainerTheme) private var theme

    let summary: String
    let previousTitle: String
    let nextTitle: String
    let canPrevious: Bool
    let canNext: Bool
    let onPrevious: () -> Void
    let onNext: () -> Void

    package init(summary: String, previousTitle: String, nextTitle: String, canPrevious: Bool, canNext: Bool, onPrevious: @escaping () -> Void, onNext: @escaping () -> Void) {
        self.summary = summary
        self.previousTitle = previousTitle
        self.nextTitle = nextTitle
        self.canPrevious = canPrevious
        self.canNext = canNext
        self.onPrevious = onPrevious
        self.onNext = onNext
    }

    package var body: some View {
        HStack(spacing: theme.compactControlSpacing) {
            Text(summary)
                .font(.caption.monospacedDigit())
                .foregroundStyle(.secondary)
            Spacer()
            Button(action: onPrevious) {
                Image(systemName: "chevron.left")
            }
            .disabled(!canPrevious)
            .help(previousTitle)
            .accessibilityLabel(previousTitle)
            Button(action: onNext) {
                Image(systemName: "chevron.right")
            }
            .disabled(!canNext)
            .help(nextTitle)
            .accessibilityLabel(nextTitle)
        }
        .buttonStyle(.borderless)
    }
}

private struct TrainerSaveEditorWindowModifier: ViewModifier {
    func body(content: Content) -> some View {
        content
            .frame(width: 980)
            .frame(minHeight: 700, idealHeight: 850, maxHeight: .infinity)
            .trainerSurface(.canvas)
            .trainerDismissTextEditingOnClickAway()
    }
}

extension View {
    package func trainerSaveEditorWindow() -> some View {
        modifier(TrainerSaveEditorWindowModifier())
    }
}
