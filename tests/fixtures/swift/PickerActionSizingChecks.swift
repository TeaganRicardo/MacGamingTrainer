import Foundation

@main struct PickerActionSizingChecks {
    static func main() {
        let pick: (CGFloat, CGFloat, CGFloat) -> CGFloat = { width, group, old in
            TrainerPickerActionSizing.width(
                rowWidth: width, labelWidth: 200, groupWidth: group,
                pickerWidth: old, minimumWidth: 216, maximumWidth: 420)
        }
        func require(_ condition: Bool, _ why: String) {
            guard condition else { fatalError(why) }
        }
        let narrow = pick(716, 420, 216)
        let wide = pick(1006, 420, 216)
        require(narrow == 288, "760pt minimum window should allocate 288pt picker")
        require(wide == 420, "1050pt window should expand to 420pt maximum")
        require(pick(716, 492, 288) == narrow, "width must not drift as picker grows")
        require(pick(1006, 624, 420) == wide, "wide width must remain stable after reflow")
        require(pick(716, 408, 216) == 300, "localized shortcut width contributes to allocation")
        require(pick(716, 320, 216) == 388, "shorter rows use available width")
        require(pick(716, 216, 216) == 420, "picker-only rows fit within policy max")
        require(pick(1, 420, 216) == 216, "undersized rows cannot yield negative picker width")
        require(pick(.nan, 420, 216) == 216, "invalid geometry stays deterministic")
        require(pick(716, 0, 0) == 216, "unmounted controls fall back to minimum")
        print("picker_action_responsive_width_policy_ok")
    }
}
