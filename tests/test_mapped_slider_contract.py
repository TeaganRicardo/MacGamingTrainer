import shutil
import subprocess
import tempfile
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SWIFTC = shutil.which("swiftc")
if not SWIFTC:
    raise SystemExit("swiftc required")

mapping = ROOT / "Sources/Core/UI/Primitives/TrainerSliderMapping.swift"
component = ROOT / "Sources/Core/UI/Primitives/TrainerMappedSlider.swift"
view = (ROOT / "Sources/Hades2/Hades2View.swift").read_text()
model = (ROOT / "Sources/Hades2/Hades2Model.swift").read_text()
snapshots = (ROOT / "Sources/Hades2/Views/Hades2ViewSnapshots.swift").read_text()

assert mapping.is_file()
assert component.is_file()
component_text = component.read_text()
assert "struct TrainerMappedSlider: View" in component_text
assert "mapping.marks" in component_text
assert ".accessibilityRepresentation" in component_text
assert "@Environment(\\.trainerTheme)" in component_text
assert ".fill(theme.accent)" in component_text
assert "Circle()\n                    .fill(Color.white)" in component_text
assert "onPreviewValue: ((Double?) -> Void)?" in component_text
assert ".accessibilityLabel(Text(accessibilityLabel))" in component_text
assert ".accessibilityHint(Text(accessibilityHint))" in component_text
assert "accessibilityLabel:" in view
assert "accessibilityHint:" in view
# Pointer lifecycle and commit counts are exercised below and by the native
# input fixture. Do not freeze an obsolete DragGesture implementation in text.
assert "TrainerMappedSlider(" in view
assert ".frame(width: 200)" in view
assert "text: gameSpeedInputBinding" in view
assert "gameSpeedSliderValue" in view
assert "gameSpeedPreview" in view
assert "onPreviewValue:" in view
for path in ("Sources/Hades/HadesTrainerView.swift", "Sources/Hades2/Hades2View.swift"):
    adapter = (ROOT / path).read_text()
    assert "TrainerMappedSlider(" in adapter
    assert "onPreviewValue:" in adapter
    assert "preview == nil" in adapter
assert "model.setGameSpeed(gameSpeedInput)" in view
assert "ForEach([0.25, 0.5, 1.0, 1.5, 2.0, 3.0]" not in view
assert "Hades2ViewInputSnapshot" not in snapshots
assert "gameSpeedInputRange = Hades2MultiplierKey.gameSpeed.range" in model

harness = r"""
import Foundation

func approx(_ a: Double, _ b: Double, _ eps: Double = 0.000001) -> Bool { abs(a - b) <= eps }
func fail(_ message: String) -> Never {
    fputs("FAIL: \(message)\n", stderr)
    exit(1)
}

let mapping = TrainerSliderMapping.anchoredLogarithmic(
    values: [0.1, 0.5, 1.0, 2.0, 5.0],
    step: 0.1,
    detents: [0.5, 1.0, 2.0],
    magnetDistance: 0.10,
    settleDistance: 0.04
)

let expectedAnchors: [(Double, Double)] = [
    (0.1, 0.0), (0.5, 0.25), (1.0, 0.5), (2.0, 0.75), (5.0, 1.0)
]
for (value, position) in expectedAnchors {
    if !approx(mapping.position(for: value), position) { fail("anchor \(value)") }
}
if mapping.marks != [0.1, 0.5, 1.0, 2.0, 5.0] { fail("visible marks") }
if !approx(mapping.position(for: 20.0), 1.0) { fail("visual clamp") }

for value in [0.1, 0.2, 0.5, 0.8, 1.0, 1.5, 2.0, 3.0, 4.4, 5.0] {
    if !approx(mapping.rawValue(at: mapping.position(for: value)), value, 0.00001) {
        fail("roundtrip \(value)")
    }
}

let one = mapping.position(for: 1.0)
let strong = one + 0.030
let soft = one + 0.070
let outside = one + 0.110

let strongMagnet = mapping.magnetizedPosition(strong)
if !(strongMagnet > one && strongMagnet < strong) { fail("magnetic pull") }
if strongMagnet - one > 0.015 { fail("magnetic pull must be perceptible") }
if strongMagnet - one < 0.003 { fail("magnet must not pin pointer motion") }

let softMagnet = mapping.magnetizedPosition(soft)
if !(softMagnet > one && softMagnet < soft) { fail("soft magnetic pull") }
if !approx(mapping.magnetizedPosition(outside), outside) { fail("magnet range") }

if !approx(mapping.settledPosition(strong), one) { fail("release snap core") }
if !approx(mapping.settledPosition(soft), softMagnet) { fail("release keeps continuous visual position") }
if !approx(mapping.settledPosition(outside), outside) { fail("release outside range") }

var previous = mapping.magnetizedPosition(one - 0.10)
for i in 1...200 {
    let p = one - 0.10 + Double(i) * 0.001
    let current = mapping.magnetizedPosition(p)
    if current + 0.0000001 < previous { fail("magnetic curve monotonic") }
    previous = current
}
if abs(mapping.magnetizedPosition(one - 0.0001) - mapping.magnetizedPosition(one + 0.0001)) > 0.0001 {
    fail("magnetic center continuity")
}
if abs(mapping.magnetizedPosition(one + 0.0999) - (one + 0.0999)) > 0.0001 {
    fail("magnetic edge continuity")
}

let freePosition = 0.37
let approximateValue = mapping.value(at: freePosition)
if !approx(mapping.settledPosition(freePosition), mapping.magnetizedPosition(freePosition)) {
    fail("non-detent position must remain continuous")
}
if approx(mapping.position(for: approximateValue), freePosition, 0.0005) {
    fail("readout quantization must not define thumb position")
}

let a = mapping.rawValue(at: 0.61)
let b = mapping.rawValue(at: 0.611)
if approx(a, b, 0.000001) { fail("continuous curve") }
if !approx(mapping.value(at: mapping.position(for: 2.36)), 2.4) { fail("effect step") }

// Test the production gesture owner with physical points, including starts
// away from the thumb, grab offsets, reversals, revocation and duplicate ends.
let geometry = TrainerSliderGeometry(width: 220, thumbDiameter: 20)
var drag = TrainerSliderDrag()
for position in [0.0, 0.25, 0.5, 0.75, 1.0] {
    drag.reset()
    let x = geometry.x(at: position)
    let previous = position < 0.5 ? 1.0 : 0.0
    guard let preview = drag.update(startX: x, pointerX: x,
        currentPosition: previous, geometry: geometry) else { fail("missing track preview") }
    if !approx(preview, position) { fail("track click retained old thumb offset") }
    guard let release = drag.finish(pointerX: x, geometry: geometry) else { fail("missing click commit") }
    if !approx(release, position) || drag.isActive { fail("click completion") }
    if drag.finish(pointerX: x, geometry: geometry) != nil { fail("duplicate end committed twice") }
}

let start = geometry.x(at: 0.5) + 7
guard let initial = drag.update(startX: start, pointerX: start,
    currentPosition: 0.5, geometry: geometry) else { fail("missing thumb press") }
if !approx(initial, 0.5) { fail("thumb grab jumped") }
for offset in [1.0, 14.0, -8.0, -9.0, 32.0, 0.0] {
    guard let position = drag.update(startX: start, pointerX: start + offset,
        currentPosition: 0.1, geometry: geometry) else { fail("missing drag update") }
    if !approx(geometry.x(at: position), geometry.x(at: 0.5) + offset) {
        fail("pointer tracking lost offset, followed an observation or lagged on reversal")
    }
}
drag.cancel()
if drag.isActive { fail("cancel retained active drag") }
if drag.update(startX: start, pointerX: start + 30,
    currentPosition: 0.1, geometry: geometry) != nil { fail("cancelled gesture restarted before release") }
if drag.finish(pointerX: start + 30, geometry: geometry) != nil { fail("cancelled gesture committed") }
if drag.update(startX: 10, pointerX: 10,
    currentPosition: 0.5, geometry: geometry) == nil { fail("new gesture did not recover") }
drag.reset()
if drag.finish(pointerX: 100, geometry: geometry) != nil { fail("system-reset gesture committed") }

for width in [0.0, 12.0, 24.0, 80.0, 800.0] {
    let narrow = TrainerSliderGeometry(width: width, thumbDiameter: 20)
    for pointer in [-100.0, 0.0, 8.0, width, width + 100] {
        let position = narrow.position(at: pointer)
        if !position.isFinite || !(0...1).contains(position) { fail("degenerate or narrow geometry") }
        let x = narrow.x(at: position)
        if !x.isFinite || x < 0 || x > max(width, 0) { fail("thumb escaped control bounds") }
    }
}

// Magnetic preview affects the value, never the pointer geometry. The release
// is then represented by the exact quantized value rather than a stale raw x.
drag.reset()
let raw = one + 0.03
guard let precise = drag.update(startX: geometry.x(at: raw), pointerX: geometry.x(at: raw),
    currentPosition: 0, geometry: geometry) else { fail("missing detent preview") }
if !approx(precise, raw) { fail("detent pinned pointer geometry") }
let final = mapping.value(at: mapping.settledPosition(drag.finish(
    pointerX: geometry.x(at: raw), geometry: geometry)!))
if !approx(final, 1.0) || !approx(mapping.position(for: final), one) { fail("detent release") }

print("mapped_slider_math_ok")
"""

with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    main = td / "main.swift"
    binary = td / "mapping-test"
    main.write_text(textwrap.dedent(harness))
    subprocess.run([SWIFTC, str(mapping), str(main), "-o", str(binary)], check=True, cwd=ROOT)
    subprocess.run([str(binary)], check=True, cwd=ROOT)

print("mapped_slider_contract_ok")
