"""Root regression for issue #653: workbench Pickers have one Core presentation owner."""

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]

picker = (ROOT / "Sources/Core/UI/Primitives/TrainerPicker.swift").read_text()
assert "enum TrainerPickerPresentationState" in picker
assert "case interactive" in picker and "case unavailable" in picker
assert "@Environment(\\.isEnabled)" in picker
assert "func trainerPicker(" in picker
assert "TrainerNativePickerPresentationProbe" in picker
assert "button.isBordered = false" in picker
assert "button.focusRingType = .none" in picker
assert "button.contentTintColor" in picker
assert "TrainerPickerIndicator" in picker

# Workbench surfaces must all pass through the shared presentation owner.
workbench_files = (
    "Sources/Core/UI/Components/TrainerResourceControls.swift",
    "Sources/Hades/HadesBoonLifecycle.swift",
    "Sources/Hades/HadesRoomsPanel.swift",
    "Sources/Hades/HadesTrainerView.swift",
    "Sources/Hades2/Hades2View.swift",
    "Sources/Hades2/Views/Hades2BoonRarityPanel.swift",
)
for relative in workbench_files:
    source = (ROOT / relative).read_text()
    raw = len(re.findall(r"(?<![A-Za-z])Picker\\s*\\(", source))
    owned = source.count(".trainerPicker(")
    assert raw == owned, f"{relative}: {raw} Pickers but {owned} Core presentation owners"
    assert ".trainerPickerWidth(" not in source, f"{relative}: width-only Picker path remains"

print("picker_presentation_contract_ok")
