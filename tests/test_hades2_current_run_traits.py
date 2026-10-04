from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
LUA = (ROOT / "Backend/games/hades2/runtime/hades.lua").read_text(encoding="utf-8")
SCHEMA = (ROOT / "Backend/games/hades2/schema.py").read_text(encoding="utf-8")
TYPES = (ROOT / "Sources/Hades2/Hades2Types.swift").read_text(encoding="utf-8")
STATE = (ROOT / "Sources/Hades2/Hades2BackendState.swift").read_text(encoding="utf-8")


# #187 remains the observation seam: current-run rows must come from the live
# hero trait table rather than the acquisition catalog or desired state.
block = LUA[LUA.index("local currentRunTraits = function()"):LUA.index("local function resolveTraitTarget")]
assert "CurrentRun.Hero.Traits" in block
assert "boons()" not in block
assert "rewards()" not in block
assert "desiredFeatures" not in block

# Identity is explicitly ephemeral and cannot be presented or persisted as a
# stable save identity.
assert 'currentRunTraitIdentityScope = "currentRunInstance"' in LUA
assert "currentRunTraitIdentityPersistent = false" in LUA
assert "traitInventoryGeneration" in LUA
assert "generationId" in block
assert "runId" in block
assert "instanceId" in block
# Presentation identity follows the game's own Trait Tray title seam without
# replacing the stable runtime routing identity in `name`.
assert "GetTraitTooltipTitle" in block
assert "displayId = displayId" in block
assert 'identityScope: "currentRunInstance"' in TYPES
assert "isPersistent: false" in TYPES

# Unknown wire capabilities fail closed in Swift instead of granting an edit.
for capability in ("TraitLevelCapability", "TraitRarityCapability", "TraitRemovalCapability"):
    assert capability in TYPES
assert "?? .none" in STATE

# The public protocol remains bounded to named trait-management commands; there
# is no generic raw-memory or raw-Lua deletion command.
for forbidden in ("remove_trait_data", "raw_remove", "delete_trait"):
    assert forbidden not in LUA
assert "TRAIT_IDENTITY_SCOPE = 'currentRunInstance'" in SCHEMA

revision = int(re.search(r"version = 1, revision = (\d+)", LUA).group(1))
previous = int(re.search(r"previousModule\.revision ~= (\d+)", LUA).group(1))
assert revision == previous

print("hades2_current_run_traits_ok")
