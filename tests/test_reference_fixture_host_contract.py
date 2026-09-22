from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
fixture = (ROOT / 'ContractFixtures/reference_module/frontend/ReferenceFixtureModule.swift').read_text()
host = (ROOT / 'Sources/Core/Host/TrainerGameModule.swift').read_text()

# The executable fixture and Host interface are the contract. GAME_MODULES.md
# documents and links them, but is not a second source of executable API shape.
assert 'static func makeModel(session: TrainerBackendSession)' in host
assert 'static func makeModel(session: TrainerBackendSession) -> ReferenceFixtureModel' in fixture
assert 'static func makeModel() -> ReferenceFixtureModel' not in fixture

print('reference_fixture_host_contract_ok')
