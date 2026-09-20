from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
fixture = (ROOT / 'ContractFixtures/reference_module/frontend/ReferenceFixtureModule.swift').read_text()
host = (ROOT / 'Sources/Core/Host/TrainerGameModule.swift').read_text()
docs = (ROOT / 'GAME_MODULES.md').read_text()

assert 'static func makeModel(session: TrainerBackendSession)' in host
assert 'static func makeModel(session: TrainerBackendSession) -> ReferenceFixtureModel' in fixture
assert 'static func makeModel() -> ReferenceFixtureModel' not in fixture
assert 'static func makeModel(session: TrainerBackendSession) -> ExampleModel' in docs
assert 'static func makeModel() -> ExampleModel' not in docs

print('reference_fixture_host_contract_ok')
