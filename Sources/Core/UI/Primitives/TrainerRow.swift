import SwiftUI

/// Shared control-row chrome for every game module. Feature/stat rows provide
/// only their inner controls; horizontal inset, minimum height, panel fill and
/// disabled/pending opacity stay host-wide.
struct TrainerRow<Content: View>: View {
    @Environment(\.trainerTheme) private var theme
    let minimumHeight: CGFloat?
    let opacity: Double
    let content: Content

    init(
        minimumHeight: CGFloat? = nil,
        opacity: Double = 1,
        @ViewBuilder content: () -> Content
    ) {
        self.minimumHeight = minimumHeight
        self.opacity = opacity
        self.content = content()
    }

    var body: some View {
        content
            .environment(\.trainerActionWidth, theme.compactActionWidth)
            .frame(maxWidth: .infinity, minHeight: minimumHeight ?? theme.rowMinimumHeight, alignment: .leading)
            .padding(.horizontal, theme.rowHorizontalPadding)
            .background(theme.panel)
            .opacity(opacity)
    }
}

struct TrainerIconLabel: View {
    @Environment(\.trainerTheme) private var theme
    let title: String
    let icon: String
    let tint: Color?
    let emphasized: Bool

    init(title: String, icon: String, tint: Color? = nil, emphasized: Bool = false) {
        self.title = title
        self.icon = icon
        self.tint = tint
        self.emphasized = emphasized
    }

    var body: some View {
        HStack(spacing: 14) {
            Image(systemName: icon)
                .font(.title3)
                .foregroundStyle(tint ?? theme.accent)
                .frame(width: 40, height: 40)
                .background((tint ?? theme.accent).opacity(emphasized ? 0.12 : 0.045), in: RoundedRectangle(cornerRadius: theme.controlCornerRadius, style: .continuous))
                .accessibilityHidden(true)
            Text(title)
                .font(.subheadline.weight(.medium))
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}

enum TrainerLabeledControlLayout: Equatable {
    case natural
    case pickerAction
}

private struct TrainerPickerRowAvailableWidthKey: PreferenceKey {
    static let defaultValue: CGFloat = 0
    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) {
        value = max(value, nextValue())
    }
}

private struct TrainerPickerRowControlWidthKey: PreferenceKey {
    static let defaultValue: CGFloat = 0
    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) {
        value = max(value, nextValue())
    }
}

struct TrainerLabeledControlRow<Controls: View>: View {
    @Environment(\.trainerTheme) private var theme
    @State private var availableWidth: CGFloat = 0
    @State private var controlsWidth: CGFloat = 0
    @State private var pickerWidth: CGFloat = 0

    private var allocatedPickerWidth: CGFloat? {
        guard layout == .pickerAction,
              availableWidth > 0, controlsWidth > 0, pickerWidth > 0 else { return nil }
        return TrainerPickerActionSizing.width(
            rowWidth: availableWidth,
            labelWidth: theme.pickerActionLabelWidth,
            groupWidth: controlsWidth,
            pickerWidth: pickerWidth,
            minimumWidth: theme.pickerStandardWidth,
            maximumWidth: theme.pickerActionMaxWidth
        )
    }

    private func updateMeasurement(_ current: inout CGFloat, to next: CGFloat) {
        guard next.isFinite, next > 0, abs(current - next) > 0.5 else { return }
        var transaction = Transaction(animation: nil)
        transaction.disablesAnimations = true
        withTransaction(transaction) { current = next }
    }
    let title: String
    let icon: String
    let tint: Color
    let emphasized: Bool
    let opacity: Double
    let helpText: String
    let layout: TrainerLabeledControlLayout
    let controls: Controls

    init(title: String, icon: String, tint: Color, emphasized: Bool,
         opacity: Double = 1, helpText: String = "",
         layout: TrainerLabeledControlLayout = .natural,
         @ViewBuilder controls: () -> Controls) {
        self.title = title
        self.icon = icon
        self.tint = tint
        self.emphasized = emphasized
        self.opacity = opacity
        self.helpText = helpText
        self.layout = layout
        self.controls = controls()
    }

    var body: some View {
        TrainerRow(opacity: opacity) {
            HStack(spacing: 16) {
                TrainerIconLabel(title: title, icon: icon, tint: tint, emphasized: emphasized)
                    .frame(width: layout == .pickerAction ? theme.pickerActionLabelWidth : nil,
                           alignment: .leading)
                    .help(helpText)
                // Only the label-to-picker gap grows. Picker, shortcut and
                // action form one trailing group with native measured widths.
                Spacer(minLength: 8)
                if layout == .pickerAction {
                    HStack(spacing: 16) {
                        controls.environment(\.trainerPickerActionWidth, allocatedPickerWidth)
                    }
                    .background {
                        GeometryReader { geometry in
                            Color.clear.preference(key: TrainerPickerRowControlWidthKey.self,
                                                   value: geometry.size.width)
                        }
                    }
                } else {
                    controls
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .background {
                GeometryReader { geometry in
                    Color.clear.preference(key: TrainerPickerRowAvailableWidthKey.self,
                                           value: geometry.size.width)
                }
            }
            .onPreferenceChange(TrainerPickerRowAvailableWidthKey.self) { width in
                updateMeasurement(&availableWidth, to: width)
            }
            .onPreferenceChange(TrainerPickerRowControlWidthKey.self) { width in
                updateMeasurement(&controlsWidth, to: width)
            }
            .onPreferenceChange(TrainerPickerAllocatedWidthKey.self) { width in
                updateMeasurement(&pickerWidth, to: width)
            }
        }
    }
}
