import Foundation

@main struct PickerActionSizingChecks {
    static func main() {
        func width(_ row: CGFloat, _ trailing: [CGFloat], _ label: CGFloat = 200) -> CGFloat {
            TrainerPickerActionSizing.width(rowWidth: row, labelWidth: label,
                trailingWidths: trailing, minimumWidth: 216, maximumWidth: 420)
        }
        func check(_ condition: Bool, _ message: String) {
            guard condition else { fatalError(message) }
        }
        // The actual 760pt container has 716pt after horizontal row insets.
        check(width(716, [83.5, 88]) == 288.5, "minimum window width allocation")
        check(width(1006, [83.5, 88]) == 420, "wide window fills capped picker lane")
        check(width(716, [95.5, 88]) == 276.5, "localized shortcut changes allocation")
        check(width(716, [88]) == 388, "missing shortcut does not create a phantom gap")
        check(width(716, []) == 420, "picker-only rows use their available lane")
        check(width(716, [72, 88]) == 300, "numeric entry rows retain trailing controls")
        check(width(716, [83.5, 88], 200) == width(716, [83.5, 88], 200), "stable after repeated layout")
        check(width(716, [83.5, 88], 230) == 258.5, "label width is accounted for")
        check(width(1, [83.5, 88]) == 216, "never allocate a negative width")
        check(width(.nan, [83.5, 88]) == 216, "non-finite proposed width fallback")
        check(width(716, [83.5, .nan]) == 216, "non-finite control fallback")

        // This was the escaped defect: aggregating a group may undercount a
        // trailing native badge; individual sizes retain the entire footprint.
        let picker = width(716, [83.5, 88])
        let occupied = 200 + 8 + 3 * 16 + picker + 83.5 + 88
        check(occupied <= 716, "trailing action group overflowed its row")
        check(occupied == 716, "narrow row should use all allocatable space")
        let wide = width(1006, [83.5, 88])
        let spare = 1006 - (200 + 8 + 3 * 16 + wide + 83.5 + 88)
        check(spare >= 0, "wide layout overflowed instead of leaving leading gap")
        print("picker_action_individual_trailing_widths_ok")
    }
}
