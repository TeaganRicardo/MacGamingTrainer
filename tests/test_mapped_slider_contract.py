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
assert "Slider(value: positionBinding, in: 0...1, onEditingChanged:" in component_text
assert ".controlSize(.regular)" in component_text
assert "mapping.marks" in component_text
assert "@State private var livePosition" in component_text
assert "@State private var isEditing" in component_text
assert "TrainerMappedSlider(" in view
assert ".frame(width: 200)" in view
assert "text: $gameSpeedInput" in view
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
    snapDistance: 0.0125
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

let two = mapping.position(for: 2.0)
if !approx(mapping.snappedPosition(two + 0.010), two) { fail("detent snap") }
if approx(mapping.snappedPosition(two + 0.020), two) { fail("reduced snap threshold") }
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
