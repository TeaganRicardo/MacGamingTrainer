from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / 'Native/ProcessTimeWarp/ProcessTimeWarp.c'
FISHHOOK = ROOT / 'Native/ProcessTimeWarp/vendor/fishhook/fishhook.c'
FISHHOOK_H = ROOT / 'Native/ProcessTimeWarp/vendor/fishhook/fishhook.h'
UPSTREAM = ROOT / 'Native/ProcessTimeWarp/vendor/fishhook/UPSTREAM'

assert HELPER.is_file(), 'native Time Warp helper is missing'
assert FISHHOOK.is_file() and FISHHOOK_H.is_file(), 'fishhook vendor source is missing'
assert 'commit aadc161ac3b80db07a9908851839a17ba63a9eb1' in UPSTREAM.read_text().splitlines()

source = HELPER.read_text()
for symbol in (
    'MGTTimeWarpABI', 'MGTTimeWarpInstall', 'MGTTimeWarpSetSpeed',
    'MGTTimeWarpGetSpeed', 'MGTTimeWarpHookMask', 'MGTTimeWarpInstallState',
):
    assert symbol in source, symbol

assert 'rebind_symbols_image(' in source
assert '_dyld_register_func_for_add_image' in source
assert 'mach_absolute_time' in source
assert 'mach_continuous_time' in source
assert 'clock_gettime' in source
assert 'CACurrentMediaTime' in source
assert '#define MGT_MIN_SPEED 0.0' in source
assert '#define MGT_MAX_SPEED 10.0' in source
assert 'anchor_real_ticks' in source and 'anchor_offset_ticks' in source
assert 'speed - 1.0' in source
assert 'basename' in source or 'image_basename' in source

# build.sh's compile, merge, signing and licence packaging of this helper is
# asserted on the executed packaging stage in test_build_signing_scope.py.

print('process_time_warp_native_contract_ok')
