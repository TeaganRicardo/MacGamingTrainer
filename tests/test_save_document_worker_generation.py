"""Documents retain display context while a replaced worker loses authority."""
import shutil
import subprocess
import tempfile
from pathlib import Path
from swift_test_compiler import SWIFT_CORE_MODULE, SwiftModule, compile_swift_test

ROOT = Path(__file__).resolve().parents[1]
HARNESS = r'''
import Foundation

let first = TrainerSaveEditorReplyCoordinator()
let second = TrainerSaveEditorReplyCoordinator()
let original = UUID(), replacement = UUID()
for owner in [first, second] {
    owner.observeBackendGeneration(original)
    owner.bind(workspaceID: "reused-workspace", baselineGeneration: "reused-baseline")
}
let firstApply = first.capture()
let secondQuery = second.capture(.query)
precondition(first.accepts(firstApply) && second.accepts(secondQuery))
for owner in [first, second] {
    precondition(owner.observeBackendGeneration(replacement))
    precondition(owner.workspaceID == "reused-workspace" && owner.baselineGeneration == "reused-baseline")
    precondition(!owner.owns(workspaceID: "reused-workspace", baselineGeneration: "reused-baseline"))
}
precondition(!first.accepts(firstApply) && !second.accepts(secondQuery))
let explicitRead = first.beginNewDocumentRead()
precondition(first.accepts(explicitRead))
first.bind(workspaceID: "reused-workspace", baselineGeneration: "reused-baseline")
precondition(first.owns(workspaceID: "reused-workspace", baselineGeneration: "reused-baseline"))
precondition(!first.accepts(firstApply) && !second.accepts(secondQuery))
let trusted = first.capture()
let queryTicket = first.capture(.query)
let detailTicket = first.capture(.detail)
first.invalidate(.query)
precondition(!first.accepts(queryTicket) && first.accepts(detailTicket) && first.accepts(trusted))
precondition(first.owns(workspaceID: "reused-workspace", baselineGeneration: "reused-baseline"))
first.invalidateDocument()
precondition(!first.accepts(trusted) && !first.owns(workspaceID: "reused-workspace", baselineGeneration: "reused-baseline"))
first.bind(workspaceID: "reused-workspace", baselineGeneration: "reused-baseline")
let activeBeforeRetire = first.capture(.detail)
let openBeforeRetire = first.capture(.open, bindsDocument: false)
precondition(first.accepts(activeBeforeRetire) && first.accepts(openBeforeRetire) && first.owns(workspaceID: "reused-workspace", baselineGeneration: "reused-baseline"))
first.retire()
precondition(!first.accepts(activeBeforeRetire) && !first.accepts(openBeforeRetire) && !first.owns(workspaceID: "reused-workspace", baselineGeneration: "reused-baseline"))
precondition(first.workspaceID == nil && first.baselineGeneration == nil)
print("save_document_worker_generation_ok")
'''
with tempfile.TemporaryDirectory(prefix='mgt-document-generation-') as directory:
    directory = Path(directory)
    main, binary = directory / 'main.swift', directory / 'generation'
    main.write_text(HARNESS)
    # Portable: the Linux lane has no SwiftUI/AppKit, so this compiles only this
    # Foundation-level file.
    compile_swift_test(
        modules=[SwiftModule(SWIFT_CORE_MODULE, [ROOT / 'Sources/Core/Save/TrainerSaveEditorReplyCoordinator.swift'])],
        harness_sources=[main], output=binary, flags=(), swiftc=shutil.which('swiftc'), cwd=ROOT,
    )
    subprocess.run([str(binary)], check=True, timeout=5)
