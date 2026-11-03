import Foundation
import SwiftUI

@main struct LayoutGeometryChecks {
    static func main() {
        let layout = TrainerPickerActionLayout(labelWidth: 200, minimumPickerWidth: 216,
                                               maximumPickerWidth: 420, minimumIntermediateWidth: 52)
        func verify(_ width: CGFloat, _ natural: [CGFloat], expectedPicker: CGFloat,
                    expectedGap: CGFloat, expectedIntermediate: CGFloat? = nil) {
            let recorders = natural.map { _ in GeometryRecorder() }
            let subviews = LayoutSubviews(natural.enumerated().map { i, w in
                LayoutSubview(natural: CGSize(width: w, height: 24), recorder: recorders[i])
            })
            var cache: () = ()
            let size = layout.sizeThatFits(proposal: ProposedViewSize(width: width, height: nil),
                                           subviews: subviews, cache: &cache)
            let bounds = CGRect(x: 0, y: 0, width: size.width, height: size.height)
            layout.placeSubviews(in: bounds, proposal: ProposedViewSize(width: width, height: nil),
                                 subviews: subviews, cache: &cache)
            let picker = recorders[1]
            let action = recorders.last!
            let pickerRight = picker.point.x + (picker.proposed.width ?? 0)
            let actionRight = action.point.x + (action.proposed.width ?? 0)
            let pickerGapToEnd = size.width - pickerRight
            print("row=\(width) natural=\(natural) picker=\(picker.proposed.width ?? 0) " +
                  "gap=\(pickerGapToEnd) buttonRight=\(actionRight)")
            precondition(abs((picker.proposed.width ?? 0) - expectedPicker) < 0.1,
                         "incorrect picker width")
            precondition(abs(pickerGapToEnd - expectedGap) < 0.1,
                         "missing intermediate-slot reservation in native row")
            precondition(abs(actionRight - size.width) < 0.1,
                         "trailing action must reach right edge")
            if let expectedIntermediate {
                precondition(abs((recorders[2].proposed.width ?? 0) - expectedIntermediate) < 0.1,
                             "intermediate control was not reserved its minimum width")
            }
        }
        verify(716, [200, 216, 83.5, 88], expectedPicker: 288.5, expectedGap: 203.5,
               expectedIntermediate: 83.5)
        verify(1006, [200, 216, 83.5, 88], expectedPicker: 420, expectedGap: 203.5,
               expectedIntermediate: 83.5)
        // Reproduce the CI escape: intrinsic badge can report 39 pt even
        // though the shared badge role promises a 52 pt minimum visual slot.
        verify(716, [200, 216, 39, 88], expectedPicker: 320, expectedGap: 172,
               expectedIntermediate: 52)
        verify(1006, [200, 216, 39, 88], expectedPicker: 420, expectedGap: 172,
               expectedIntermediate: 52)
        // A truly absent badge must not create a phantom slot or spacing.
        verify(716, [200, 216, 0, 88], expectedPicker: 388, expectedGap: 104)
        verify(716, [200, 216, 72, 88], expectedPicker: 300, expectedGap: 192,
               expectedIntermediate: 72)
        print("native_layout_minimum_intermediate_width_ok")
    }
}
