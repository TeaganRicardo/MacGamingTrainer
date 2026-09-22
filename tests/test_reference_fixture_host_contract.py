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


# Game-specific management commands belong to the module, not the Host model.
assert 'associatedtype ManagementCommands: Commands' in host
assert 'static func makeManagementCommands(model: Model) -> ManagementCommands' in host
for legacy in ('func disableAllFromHost()', 'func openLog()'):
    assert legacy not in host, legacy
assert 'static func makeManagementCommands(model: ReferenceFixtureModel)' in fixture
assert 'func disableAllFromHost()' not in fixture
assert 'func openLog()' not in fixture
