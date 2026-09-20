from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
app = (ROOT / "Sources/App.swift").read_text()
module = (ROOT / "Sources/Core/Host/TrainerGameModule.swift").read_text()
hades_module = (ROOT / "Sources/Hades2/Hades2Module.swift").read_text()
model = (ROOT / "Sources/Hades2/Hades2Model.swift").read_text()

assert app.count("TrainerBackendSession()") == 1, "App must own exactly one backend session"
assert "makeModel(session: backendSession)" in app
assert "static func makeModel(session: TrainerBackendSession) -> Model" in module
assert "static func makeModel(session: TrainerBackendSession)" in hades_module
assert "private let backendSession = TrainerBackendSession()" not in model
assert "private let backendSession: TrainerBackendSession" in model
assert "init(session: TrainerBackendSession)" in model

print("shared_backend_session_round20_ok")
