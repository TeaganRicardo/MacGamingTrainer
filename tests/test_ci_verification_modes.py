import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = {
    "linux": ROOT / ".github/workflows/linux-contracts.yml",
    "macos": ROOT / ".github/workflows/build2-macos.yml",
    "module": ROOT / ".github/workflows/module-build-matrix.yml",
}

for name, path in WORKFLOWS.items():
    text = path.read_text(encoding="utf-8")
    trigger = text.split("\npermissions:", 1)[0]
    assert "pull_request:" in trigger, f"{name}: PR task verification trigger missing"
    assert "workflow_dispatch:" in trigger, f"{name}: explicit convergence trigger missing"
    assert not re.search(r"^  push:\s*$", trigger, re.M), (
        f"{name}: merged main must not automatically rerun task verification"
    )

linux = WORKFLOWS["linux"].read_text(encoding="utf-8")
assert 'python3 Tools/check_runtime_revision.py "$BASE_SHA" "$HEAD_SHA"' in linux
assert "bash Tools/run_linux_checks.sh" in linux

macos = WORKFLOWS["macos"].read_text(encoding="utf-8")
for step in (
    "Verify declared invariants fail under mutation",
    "Package release candidate",
    "Verify release provenance and checksum",
    "actions/upload-artifact@v4",
):
    pos = macos.index(step)
    window = macos[pos:pos + 700]
    assert "github.event_name == 'workflow_dispatch'" in window, (
        f"Build 2 heavy convergence step is not dispatch-only: {step}"
    )
assert "Run macOS-only contract suite" in macos
assert "Build Hades II trainer" in macos
assert "Verify package" in macos

module = WORKFLOWS["module"].read_text(encoding="utf-8")
assert "Build selected module" in module
assert "Verify packaged module isolation" in module
for step in (
    "Retain reference module artifact and source provenance",
    "Verify reference artifact checksum and declared inputs",
    "actions/upload-artifact@v4",
):
    pos = module.index(step)
    window = module[pos:pos + 700]
    assert "github.event_name == 'workflow_dispatch'" in window, (
        f"reference convergence artifact step is not dispatch-only: {step}"
    )

print("ci_verification_modes_ok")
