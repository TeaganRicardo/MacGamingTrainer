"""Documents retain display context while a replaced worker loses authority."""
import shutil
import subprocess
import tempfile
from pathlib import Path

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
first.invalidateDocument()
precondition(!first.accepts(trusted) && !first.owns(workspaceID: "reused-workspace", baselineGeneration: "reused-baseline"))
print("save_document_worker_generation_ok")
'''
with tempfile.TemporaryDirectory(prefix='mgt-document-generation-') as directory:
    directory = Path(directory)
    main, binary = directory / 'main.swift', directory / 'generation'
    main.write_text(HARNESS)
    subprocess.run([shutil.which('swiftc'), str(ROOT / 'Sources/Core/Save/TrainerSaveEditorReplyCoordinator.swift'),
        str(main), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True, timeout=5)
