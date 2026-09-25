from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / 'Native/ProcessTimeWarp/ProcessTimeWarp.c'
FISHHOOK = ROOT / 'Native/ProcessTimeWarp/vendor/fishhook/fishhook.c'
FISHHOOK_H = ROOT / 'Native/ProcessTimeWarp/vendor/fishhook/fishhook.h'
UPSTREAM = ROOT / 'Native/ProcessTimeWarp/vendor/fishhook/UPSTREAM'
BUILD = (ROOT / 'build.sh').read_text()

assert HELPER.is_file(), 'native Time Warp helper is missing'
assert FISHHOOK.is_file() and FISHHOOK_H.is_file(), 'fishhook vendor source is missing'
assert UPSTREAM.read_text().strip().endswith('aadc161ac3b80db07a9908851839a17ba63a9eb1')

source = HELPER.read_text()
for symbol in (
    'MGTTimeWarpABI', 'MGTTimeWarpInstall', 'MGTTimeWarpSetSpeed',
    'MGTTimeWarpGetSpeed', 'MGTTimeWarpHookMask',
):
    assert symbol in source, symbol

assert 'rebind_symbols_image(' in source
assert '_dyld_register_func_for_add_image' in source
assert 'uint32_t count = _dyld_image_count();' in source
assert 'rebind_selected_image(_dyld_get_image_header(index), _dyld_get_image_vmaddr_slide(index));' in source
assert 'atomic_store_explicit(&callback_registered, false' not in source
assert 'mach_absolute_time' in source
assert 'mach_continuous_time' in source
assert 'clock_gettime' in source
assert 'CACurrentMediaTime' in source
assert '#define MGT_MIN_SPEED 0.0' in source
assert '#define MGT_MAX_SPEED 10.0' in source
assert 'anchor_real_ticks' in source and 'anchor_offset_ticks' in source
assert 'speed - 1.0' in source
assert 'basename' in source or 'image_basename' in source

for token in (
    'TIME_WARP_ROOT="$ROOT/Native/ProcessTimeWarp"',
    'TIME_WARP_SOURCE="$TIME_WARP_ROOT/ProcessTimeWarp.c"',
    'TIME_WARP_FISHHOOK="$TIME_WARP_ROOT/vendor/fishhook/fishhook.c"',
    '-dynamiclib',
    '-isysroot "$SDK"',
    '-framework QuartzCore',
    'libMGTTimeWarp.dylib',
    'codesign --force --sign - --timestamp=none "$TIME_WARP_DYLIB"',
    'LICENSE.fishhook',
):

    assert token in BUILD, token

print('process_time_warp_native_contract_ok')