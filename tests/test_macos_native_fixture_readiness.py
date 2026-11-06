"""Native fixtures reach readiness through the event loop, not a busy poll.

These are the semantic-readiness invariants that the retired outer-timeout
budget test also happened to guard. Outer watchdog values live in
`tests/macos_fixture_policy.py`; nothing here asserts a duration.
"""
from pathlib import Path

TESTS = Path(__file__).resolve().parent

real_navigation = (TESTS / "real_module_navigation_harness.py").read_text(encoding="utf-8")
assert "RunLoop.current.run(until:" in real_navigation
assert "NSApp.nextEvent(matching: .any" not in real_navigation
assert 'journeyWait("visible native Host and both real module backends"' in real_navigation
assert "app.isActive && window.isKeyWindow && first.backendAvailable" not in real_navigation
assert 'journeyWait("actual context tool window") { tool.isVisible }' in real_navigation

runtime_text_edit = (TESTS / "test_runtime_text_edit_completion.py").read_text(encoding="utf-8")
assert "func runRuntimeTextEditJourney() throws" in runtime_text_edit
assert 'check(NSApp.isRunning,"runtime text-edit fixture did not enter the AppKit application event loop")' in runtime_text_edit
assert "app.run()" in runtime_text_edit
assert runtime_text_edit.count("@main struct Main") == 1
assert 'phase("editing:complete")\n }\n\n@main struct Main' in runtime_text_edit
assert 'wait("native Hades II selected-trait inputs did not mount")' in runtime_text_edit
assert 'wait("native trait selection did not mount the replacement level input")' in runtime_text_edit
assert 'wait("trait observation did not mount the replacement remaining-use input")' in runtime_text_edit
assert 'wait("material owner replacement did not reset the displayed amount")' in runtime_text_edit
assert 'wait("restored material owner did not restore its observed amount")' in runtime_text_edit
assert 'model.currentRunTraits=[firstTrait,secondTrait];pump()' not in runtime_text_edit
assert 'phase("editing:material:replace-owner:assigned"); pump()' not in runtime_text_edit
assert "import Darwin" in runtime_text_edit
assert "fflush(nil)" in runtime_text_edit
assert "Darwin._exit(0)" in runtime_text_edit

native_picker = (TESTS / "native_picker_harness.py").read_text(encoding="utf-8")
assert "if case .accessibility = opening" in native_picker
assert "accessibility picker selection requires the AppKit application event loop" in native_picker
assert "guard let highlightedTitle, let highlightedIndex else { return }" in native_picker
assert "(highlightedIndex ?? -1) < destinationIndex" not in native_picker

disclosure = (TESTS / "disclosure_ui_harness.py").read_text(encoding="utf-8")
assert "let retainedPublicationDeadline = Date().addingTimeInterval(1)" in disclosure
assert "let retirementDeadline = Date().addingTimeInterval(1)" in disclosure
assert "while Date() < retirementDeadline" in disclosure
assert "if settled { break }" in disclosure
assert "disclosureLifetimePump(0.01)" in disclosure
assert "disclosureLifetimePump(0.03)" not in disclosure

print("macos_native_fixture_readiness_ok")
