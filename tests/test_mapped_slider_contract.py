from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap

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
assert "DragGesture(minimumDistance: 0)" in component_text
assert "@State private var displayPosition" in component_text
assert "@State private var dragOffset" in component_text
assert "mapping.marks" in component_text
assert ".interactiveSpring(" in component_text
assert ".accessibilityRepresentation" in component_text
assert "@Environment(\\.trainerTheme)" in component_text
assert ".fill(theme.accent)" in component_text
changed_block = component_text[component_text.index(".onChanged"):component_text.index(".onEnded")]
ended_block = component_text[component_text.index(".onEnded"):component_text.index(".accessibilityRepresentation")]
assert "commit(" not in changed_block
assert "value =" not in changed_block
assert "commit(" in ended_block
assert "TrainerMappedSlider(" in view
assert ".frame(width: 200)" in view
assert "text: $gameSpeedInput" in view
assert "gameSpeedSliderValue" in view
assert "gameSpeedInput: gameSpeedInput" in view
assert "ForEach([0.25, 0.5, 1.0, 1.5, 2.0, 3.0]" not in view
assert "gameSpeedInput" in snapshots
assert 'coalesceKey: "feature.gameSpeed"' in model
assert "gameSpeedInputRange = 0.0...10.0" in model

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
    magnetDistance: 0.075,
    settleDistance: 0.035
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
let soft = one + 0.060
let outside = one + 0.080

let strongMagnet = mapping.magnetizedPosition(strong)
if !(strongMagnet > one && strongMagnet < strong) { fail("magnetic pull") }
if strongMagnet - one < 0.008 { fail("magnet must not pin pointer motion") }

let softMagnet = mapping.magnetizedPosition(soft)
if !(softMagnet > one && softMagnet < soft) { fail("soft magnetic pull") }
if !approx(mapping.magnetizedPosition(outside), outside) { fail("magnet range") }

if !approx(mapping.settledPosition(strong), one) { fail("release snap core") }
if !approx(mapping.settledPosition(soft), softMagnet) { fail("release keeps continuous visual position") }
if !approx(mapping.settledPosition(outside), outside) { fail("release outside range") }

var previous = mapping.magnetizedPosition(one - 0.075)
for i in 1...150 {
    let p = one - 0.075 + Double(i) * 0.001
    let current = mapping.magnetizedPosition(p)
    if current + 0.0000001 < previous { fail("magnetic curve monotonic") }
    previous = current
}
if abs(mapping.magnetizedPosition(one - 0.0001) - mapping.magnetizedPosition(one + 0.0001)) > 0.0001 {
    fail("magnetic center continuity")
}
if abs(mapping.magnetizedPosition(one + 0.0749) - (one + 0.0749)) > 0.0001 {
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
