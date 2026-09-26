from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
build = (ROOT / "build.sh").read_text()
start = build.index('    "$CLANG"')
end = build.index('    TIME_WARP_ARCH_BINARIES+=("$helper")', start)
compile_command = build[start:end]

assert "-Wall" in compile_command
assert "-Wextra" in compile_command
assert "-Werror" not in compile_command
assert '"$TIME_WARP_SOURCE" "$TIME_WARP_FISHHOOK"' in compile_command

print("native_clang_warning_contract_ok")
