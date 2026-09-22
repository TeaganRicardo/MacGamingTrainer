from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
lua = (ROOT / "Backend/games/hades2/runtime/hades.lua").read_text(encoding="utf-8")

required = {
    "projectile cap": "ActiveProjectileCap = 32",
    "native multicast control": "nativeMultiCastControlSet",
    "resource-spent table guard": 'type(CurrentRun.ResourcesSpent) == "table"',
    "stat availability projection": "statAvailable = statAvailable",
}
for name, token in required.items():
    assert token in lua, f"{name}: missing resident contract token {token!r}"

print("hades2_runtime_static_contract_ok")
