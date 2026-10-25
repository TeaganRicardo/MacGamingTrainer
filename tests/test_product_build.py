"""Exercise selection, generation and package identity across two real-shaped modules."""
import json
import plistlib
import shutil
import sys
import tempfile
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Tools'))
import module_support
import product_support
import verify_module_build
from generate_game_binding import generate
from module_support import ManifestError
from build_module_native import build_libraries


with tempfile.TemporaryDirectory(prefix='mgt-product-build-') as temporary:
    project = Path(temporary)
    (project / 'Info.plist').write_bytes(plistlib.dumps({'CFBundleExecutable': 'Trainer'}))
    (project / 'Tools').mkdir()
    shutil.copy2(ROOT / 'Tools/python_runtime.json', project / 'Tools/python_runtime.json')
    product = {
        'schemaVersion': 1,
        'app': {'bundleIdentifier': 'com.example.trainer', 'displayName': 'Unified Trainer'},
        'architectures': ['arm64'], 'minimumMacOS': '14.0', 'modules': ['one', 'two'],
    }
    (project / 'app.json').write_text(json.dumps(product))
    for name in product['modules']:
        backend = project / 'Backend/games' / name
        backend.mkdir(parents=True)
        frontend = project / 'Sources' / name
        frontend.mkdir(parents=True)
        native = backend / 'native'
        native.mkdir()
        (native / 'Bridge.c').write_text('int bridge(void) { return 0; }\n')
        data = {
            'schemaVersion': 1, 'id': name, 'displayName': name.title(), 'protocolVersion': 1,
            'backend': {'adapter': f'games.{name}.adapter:Adapter'},
            'frontend': {'sourceDirectory': f'Sources/{name}', 'moduleType': f'{name.title()}Module',
                         'architectures': ['x86_64'], 'minimumMacOS': '14.0'},
            'targetApplication': {'processName': 'Game.macOS', 'bundleIdentifier': '',
                                  'executablePathSuffix': f'{name}/Game.macOS'},
            'nativeLibraries': [{'source': 'native/Bridge.c', 'filename': 'libBridge.dylib',
                                 'architectures': ['x86_64']}],
        }
        (backend / 'module.json').write_text(json.dumps(data))
    module_support.ROOT = project
    product_support.ROOT = project
    verify_module_build.ROOT = project

    selection = product_support.load_selection()
    assert selection.ids == ('one', 'two')
    assert selection.architectures == ('arm64',)
    assert all(module.native_libraries[0].architectures == ('x86_64',) for module in selection.modules)
    assert selection.modules[0].runtime.bundle_identifier == ''
    assert selection.modules[0].runtime.public_metadata()['targetApplication']['executablePathSuffix'] == 'one/Game.macOS'
    assert product_support.load_selection('one').ids == ('one',)
    compiled_arches = []
    def run_native_tool(command, **kwargs):
        if command[0] == 'fixture-clang':
            compiled_arches.append(command[command.index('-arch') + 1])
            Path(command[command.index('-o') + 1]).write_bytes(b'compiled library fixture')
    with patch('build_module_native.subprocess.run', side_effect=run_native_tool):
        build_libraries(module_support.normalized_manifest(selection.modules[0]),
                        project / 'Backend/games/one', project,
                        clang='fixture-clang', sdk='fixture-sdk',
                        architectures=['arm64'], minimum_macos='14.0')
    assert compiled_arches == ['x86_64']

    output = project / 'Generated.swift'
    generate(selection.modules, output, catalog=True)
    generated = output.read_text()
    for module in ('OneModule', 'TwoModule'):
        assert f'TrainerGameContext<{module}>()' in generated
        assert f'{module}.makeManagementCommands(model: context.model' in generated
    assert 'typealias ActiveGameModule' not in generated
    assert 'targetExecutablePathSuffix: "one/Game.macOS"' in generated

    dist = project / 'dist'
    app = dist / 'Unified Trainer.app'
    resources = app / 'Contents/Resources'
    for module in selection.modules:
        packaged = resources / 'Backend/games' / module.id
        shutil.copytree(module.runtime.source_path.parent, packaged)
        (packaged / 'native/libBridge.dylib').write_bytes(b'fixture library')
    (resources / 'ACTIVE_GAME_ID').write_text('one\n')
    (resources / 'GAME_MODULES.json').write_text(json.dumps(['one', 'two']))
    executable = app / 'Contents/MacOS/Trainer'
    executable.parent.mkdir()
    executable.write_bytes(b'fixture executable')
    info = {
        'CFBundleExecutable': 'Trainer', 'CFBundleIdentifier': 'com.example.trainer',
        'CFBundleName': 'Unified Trainer', 'CFBundleDisplayName': 'Unified Trainer',
    }
    (app / 'Contents/Info.plist').write_bytes(plistlib.dumps(info))
    runtime_source = json.loads((ROOT / 'Tools/python_runtime.json').read_text())
    runtime = resources / 'Python'
    interpreter = runtime / 'arm64/bin/python3'
    interpreter.parent.mkdir(parents=True)
    interpreter.write_text('#!/bin/sh\nexit 0\n')
    interpreter.chmod(0o755)
    (runtime / 'runtime.json').write_text(json.dumps({
        **{key: runtime_source[key] for key in ('schemaVersion', 'provider', 'release', 'version')},
        'architectures': ['arm64'],
        'distributions': {'arm64': runtime_source['distributions']['arm64']},
    }))
    assert verify_module_build.verify_module_build('all', dist) == app.resolve()
    (resources / 'GAME_MODULES.json').write_text(json.dumps(['one']))
    try:
        verify_module_build.verify_module_build('all', dist)
    except ValueError as error:
        assert 'module set' in str(error)
    else:
        raise AssertionError('A package missing the second game was accepted')

    # A case-insensitive destination collision fails before any App is copied.
    resource = project / 'shared.txt'
    resource.write_text('source')
    for name, destination in (('one', 'Shared.json'), ('two', 'shared.json')):
        manifest = project / 'Backend/games' / name / 'module.json'
        data = json.loads(manifest.read_text())
        data['appResources'] = [{'source': 'shared.txt', 'destination': destination}]
        manifest.write_text(json.dumps(data))
    try:
        product_support.load_selection()
    except ManifestError as error:
        assert 'shared by one and two' in str(error)
    else:
        raise AssertionError('Conflicting module resource destinations were accepted')

print('product_build_ok')
