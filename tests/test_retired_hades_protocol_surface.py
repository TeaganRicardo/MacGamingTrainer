from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
paths = (
    "Sources/Hades2/Hades2API.swift",
    "Sources/Hades2/Hades2Model.swift",
    "Sources/Hades2/Hades2BackendState.swift",
    "Backend/games/hades2/adapter.py",
    "Backend/games/hades2/command_router.py",
    "Backend/games/hades2/runtime/hades.lua",
)
product_text = "\n".join((ROOT / path).read_text(encoding="utf-8") for path in paths)

for retired in ("boonChoice", "set_boon_choice", "spawn_boon", "add_resource"):
    assert retired not in product_text, f"retired Hades protocol surface resurfaced: {retired}"

print("retired_hades_protocol_surface_ok")
