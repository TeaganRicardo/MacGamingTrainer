from pathlib import Path
import json
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
game_id = 'other_test'
backend_module = root/'Backend/games'/game_id
frontend = root/'Sources/OtherTest'
assert not backend_module.exists() and not frontend.exists()
backend_module.mkdir(parents=True); frontend.mkdir(parents=True)
try:
    (backend_module/'__init__.py').write_text('')
    (backend_module/'adapter.py').write_text('''\nfrom core.adapter import GameAdapter\nclass OtherAdapter(GameAdapter):\n    def dispatch(self, command, params, request_id): return {"command": command}\n    def close(self): pass\n''')
    (backend_module/'module.json').write_text(json.dumps({
        'id':game_id,'displayName':'Other Test Game','protocolVersion':3,
        'backend':{'adapter':f'games.{game_id}.adapter:OtherAdapter'},
        'targetApplication':{'processName':'Other Test Game','bundleIdentifier':'com.example.othertest'},
        'frontend':{'sourceDirectory':'Sources/OtherTest','moduleType':'OtherTestModule','minimumMacOS':'14.0'},
        'buildRequirements':{'lldbPython':False,'debuggerEntitlement':False},
    }))
    (frontend/'OtherTestModule.swift').write_text('''
import SwiftUI

final class OtherTestModel: ObservableObject, TrainerHostModel {
    @Published var backendAvailable = true
    @Published var busy = false
    @Published var connected = false
    @Published var enabled = false
    func connectFromHost() { connected = true }
    func refreshFromHost() { }
    func disableAllFromHost() { enabled = false }
    func openLog() { }
    func prepareForTermination(completion: @escaping (Bool) -> Void) { completion(true) }
}

struct OtherTestContent: View {
    @ObservedObject var model: OtherTestModel
    var body: some View {
        TrainerCard {
            TrainerRow {
                Text("Example Feature")
            } trailing: {
                TrainerToggleControl(isOn: model.enabled, enabled: true) { model.enabled.toggle() }
            }
        }
    }
}

struct OtherTestModule: TrainerGameModule {
    static let presentation = TrainerGamePresentation(headerTitle: "OTHER")
    static func makeModel() -> OtherTestModel { OtherTestModel() }
    static func makeContent(model: OtherTestModel) -> OtherTestContent { OtherTestContent(model: model) }
    static func makeSidebarActions(model: OtherTestModel) -> some View { EmptyView() }
    static func makeHeaderActions(model: OtherTestModel) -> some View { EmptyView() }
}
''')

    normalized = json.loads(subprocess.check_output([
        'python3', str(root/'Tools/validate_game_module.py'), game_id, '--json'
    ], text=True))
    assert normalized['id'] == game_id
    assert normalized['buildRequirements']['lldbPython'] is False

    generated = Path(tempfile.mkstemp(suffix='.swift')[1])
    try:
        subprocess.run(['python3', str(root/'Tools/generate_game_binding.py'), game_id, str(generated)], check=True)
        text = generated.read_text()
        assert 'typealias ActiveGameModule = OtherTestModule' in text
        assert 'expectedHostProtocolVersion: 5' in text
        assert 'expectedModuleProtocolVersion: 3' in text
        # Source graph uses the exact same App/Core with no Other-game branch.
        core = sorted((root/'Sources/Core').rglob('*.swift'))
        sources = [root/'Sources/App.swift'] + core + [frontend/'OtherTestModule.swift', generated]
        if shutil.which('swiftc'):
            subprocess.run(['swiftc','-frontend','-parse',*map(str,sources)],check=True)
    finally:
        generated.unlink(missing_ok=True)

    generic = (root/'Sources/App.swift').read_text() + '\n' + '\n'.join(p.read_text() for p in (root/'Sources/Core').rglob('*.swift')) + (root/'build.sh').read_text()
    assert 'OtherTest' not in generic and 'other_test' not in generic
finally:
    shutil.rmtree(backend_module, ignore_errors=True)
    shutil.rmtree(frontend, ignore_errors=True)

print('module_contract_round13_ok')
