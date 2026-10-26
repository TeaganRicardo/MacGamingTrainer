"""Decode the Hades process-speed projection and keep its control discoverable."""
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
types_source = (ROOT / 'Sources/Hades/HadesTypes.swift').read_text()
start = types_source.index('enum HadesFeatureValue: Decodable, Equatable {')
end = types_source.index('\nstruct HadesHeroTarget', start)
enum_source = types_source[start:end]
payload = {
    'gameSpeed': {'desired': 2.5, 'actual': 2.5, 'active': True,
                  'errorPresentation': None, 'errorArguments': []},
    'gameSpeedPending': {'desired': 4.0, 'actual': 2.5, 'active': True,
                         'errorPresentation': 'host.timeWarp.error.setFailed', 'errorArguments': ['7']},
    'gameSpeedUnknown': {'desired': 3.0, 'actual': None, 'active': None,
                         'errorPresentation': 'host.timeWarp.error.outcomeUnknown', 'errorArguments': ['x']},
    'moneyNoDecrease': True,
    'damageMultiplier': 3.0,
}
harness = '''
import Foundation
''' + enum_source + '''
let data = try Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1]))
let values = try JSONDecoder().decode([String: HadesFeatureValue].self, from: data)
guard values["gameSpeed"]?.number == 2.5,
      values["gameSpeed"]?.actualNumber == 2.5,
      values["gameSpeed"]?.bool == true,
      values["gameSpeed"]?.errorPresentation == nil else { fatalError("active speed projection decode failed") }
guard values["gameSpeedPending"]?.number == 4.0,
      values["gameSpeedPending"]?.actualNumber == 2.5,
      values["gameSpeedPending"]?.errorPresentation == "host.timeWarp.error.setFailed",
      values["gameSpeedPending"]?.errorArguments == ["7"] else { fatalError("pending speed projection decode failed") }
guard values["gameSpeedUnknown"]?.number == 3.0,
      values["gameSpeedUnknown"]?.actualNumber == nil,
      values["gameSpeedUnknown"]?.bool == false,
      values["gameSpeedUnknown"]?.errorPresentation == "host.timeWarp.error.outcomeUnknown" else { fatalError("unknown speed projection decode failed") }
guard values["moneyNoDecrease"]?.bool == true,
      values["damageMultiplier"]?.number == 3.0 else { fatalError("legacy feature decoding regressed") }
print("hades_game_speed_projection_decode_ok")
'''
with tempfile.TemporaryDirectory(prefix='hades-speed-swift-') as temp:
    root = Path(temp)
    swift = root / 'main.swift'
    data = root / 'state.json'
    binary = root / 'test'
    swift.write_text(harness)
    data.write_text(json.dumps(payload))
    result = subprocess.run(['swiftc', str(swift), '-o', str(binary)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    result = subprocess.run([str(binary), str(data)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    print(result.stdout.strip())

view = (ROOT / 'Sources/Hades/HadesTrainerView.swift').read_text()
nav = (ROOT / 'Sources/Hades/HadesWorkbenchNavigation.swift').read_text()
assert 'TrainerMappedSlider(' in view and 'model.setFeature(.gameSpeed' in view
assert 'host.timeWarp.title' in nav and '(.common, ["host.timeWarp.title"])' in nav
assert 'gameSpeed' not in (ROOT / 'Backend/games/hades/runtime.lua').read_text().split('local resourceNames', 1)[0].split('local defaults = {', 1)[1], \
    'process-owned game speed leaked into resident Lua defaults'
print('hades_game_speed_control_discovery_and_ownership_ok')
