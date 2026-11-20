"""Linux regression: native Picker allocation uses individual trailing widths."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from swift_test_compiler import SWIFT_CORE_MODULE, SwiftModule, compile_swift_test

ROOT = Path(__file__).resolve().parents[1]
ROW = ROOT / 'Sources/Core/UI/Primitives/TrainerRow.swift'
LAYOUT = ROOT / 'Sources/Core/UI/TrainerPickerActionLayout.swift'
HELPER = ROOT / 'Sources/Core/UI/TrainerPickerActionSizing.swift'

for path in [LAYOUT, ROW, HELPER]:
    subprocess.run(['swiftc','-frontend','-parse',str(path)],check=True,timeout=15)
if shutil.which('swiftc'):
    with tempfile.TemporaryDirectory(prefix='mgt-picker-native-width-') as tmp:
        executable = str(Path(tmp) / 'check')
        # Portable: the Linux lane has no SwiftUI/AppKit, so this compiles only these
        # Foundation-level files.
        compile_swift_test(
            modules=[SwiftModule(SWIFT_CORE_MODULE, [HELPER])],
            harness_sources=[ROOT / 'tests/fixtures/swift/PickerActionSizingChecks.swift'],
            output=Path(executable), cwd=ROOT,
        )
        subprocess.run([executable],check=True,timeout=10)
        # Exercise the production Layout against a small SwiftUI type shim on
        # Linux: an intrinsic 39pt shortcut must reserve a 52pt visual lane.
        shim_name = 'libSwiftUI.dylib' if sys.platform == 'darwin' else 'libSwiftUI.so'
        shim_library = str(Path(tmp) / shim_name)
        shim_module = str(Path(tmp) / 'SwiftUI.swiftmodule')
        swift_fixtures = ROOT / 'tests/fixtures/swift'
        build_shim = [
            'swiftc', '-emit-library', '-emit-module',
            '-module-name', 'SwiftUI',
            str(swift_fixtures / 'PickerActionLayoutMock.swift'),
            '-emit-module-path', shim_module,
            '-o', shim_library,
        ]
        if sys.platform == 'darwin':
            build_shim += ['-Xlinker', '-install_name', '-Xlinker', f'@rpath/{shim_name}']
        subprocess.run(build_shim, check=True, timeout=40)
        layout_executable = str(Path(tmp) / 'layout-check')
        # Direct swiftc: the SwiftUI type shim stands in for a system module, so
        # these Core files must compile with the same plain invocation (and SDK)
        # that built the shim above, not as a cached product module.
        subprocess.run(['swiftc', '-I', tmp, '-L', tmp, '-lSwiftUI',
                        '-Xlinker', '-rpath', '-Xlinker', tmp,
                        str(HELPER), str(LAYOUT),
                        str(swift_fixtures / 'PickerActionLayoutGeometryChecks.swift'),
                        '-o', layout_executable], check=True, timeout=40)
        subprocess.run([layout_executable], check=True, timeout=10)

print('picker_action_subview_geometry_contract_ok')
