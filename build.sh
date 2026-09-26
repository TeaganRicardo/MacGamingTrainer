#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
EXECUTABLE="MacGamingTrainer"
MODULE_VALIDATOR="${ROOT}/Tools/validate_game_module.py"
BINDING_GENERATOR="${ROOT}/Tools/generate_game_binding.py"

for tool in xcrun xcode-select codesign plutil grep find uname; do
    command -v "$tool" >/dev/null 2>&1 || { echo "Missing required tool: $tool" >&2; exit 1; }
done

SDK="$(xcrun --sdk macosx --show-sdk-path)"
SWIFTC="$(xcrun --find swiftc)"
CLANG="$(xcrun --find clang 2>/dev/null || true)"
PYTHON="$(xcrun --find python3 2>/dev/null || true)"
[[ -n "$CLANG" ]] || { echo "Xcode developer tools must provide clang." >&2; exit 1; }
[[ -n "$PYTHON" ]] || { echo "Xcode developer tools must provide python3." >&2; exit 1; }
[[ -x "$MODULE_VALIDATOR" && -x "$BINDING_GENERATOR" ]] || { echo "Missing game module build tools under Tools/." >&2; exit 1; }

DEFAULT_GAME_ID="$(tr -d '[:space:]' < "$ROOT/ACTIVE_GAME_ID")"
ACTIVE_GAME_ID="${1:-${MGT_GAME_ID:-$DEFAULT_GAME_ID}}"
[[ -n "$ACTIVE_GAME_ID" ]] || { echo "No game module selected. Pass ./build.sh <game-id> or set ACTIVE_GAME_ID." >&2; exit 1; }
if [[ $# -gt 1 ]]; then
    echo "Usage: ./build.sh [game-id]" >&2
    exit 2
fi

GENERATED_DIR="$(mktemp -d "${TMPDIR:-/tmp}/mgt-build.XXXXXX")"
trap 'rm -rf "$GENERATED_DIR"' EXIT
NORMALIZED_MANIFEST="$GENERATED_DIR/module.normalized.json"
"$PYTHON" "$MODULE_VALIDATOR" "$ACTIVE_GAME_ID" --json > "$NORMALIZED_MANIFEST"

manifest_field() {
    "$PYTHON" - "$NORMALIZED_MANIFEST" "$1" <<'PY'
import json, sys
value = json.load(open(sys.argv[1], encoding='utf-8'))
for part in sys.argv[2].split('.'):
    value = value.get(part) if isinstance(value, dict) else None
    if value is None:
        break
if isinstance(value, bool):
    print('1' if value else '0')
elif isinstance(value, list):
    print(' '.join(str(item) for item in value))
elif value is None:
    print('')
else:
    print(value)
PY
}

FRONTEND_DIR_REL="$(manifest_field frontend.sourceDirectory)"
FRONTEND_MODULE_TYPE="$(manifest_field frontend.moduleType)"
ARCHITECTURES_RAW="$(manifest_field frontend.architectures)"
MIN_MACOS="$(manifest_field frontend.minimumMacOS)"
APP_BUNDLE_ID="$(manifest_field app.bundleIdentifier)"
APP_NAME="$(manifest_field app.displayName)"
REQUIRES_LLDB="$(manifest_field buildRequirements.lldbPython)"
REQUIRES_DEBUGGER_ENTITLEMENT="$(manifest_field buildRequirements.debuggerEntitlement)"
ENTITLEMENTS_REL="$(manifest_field buildRequirements.entitlements)"
FRONTEND_DIR="$ROOT/$FRONTEND_DIR_REL"

[[ -n "$FRONTEND_DIR_REL" && -d "$FRONTEND_DIR" ]] || { echo "Missing selected frontend source directory: $FRONTEND_DIR" >&2; exit 1; }
[[ -n "$FRONTEND_MODULE_TYPE" ]] || { echo "Missing frontend module type." >&2; exit 1; }
[[ -n "$APP_NAME" && "$APP_NAME" != *'/'* ]] || { echo "Invalid app display name from module manifest." >&2; exit 1; }
[[ -n "$APP_BUNDLE_ID" ]] || { echo "Missing app bundle identifier." >&2; exit 1; }
[[ -n "$MIN_MACOS" ]] || MIN_MACOS="14.0"
[[ -n "$ARCHITECTURES_RAW" ]] || ARCHITECTURES_RAW="$(uname -m)"
read -r -a ARCHITECTURES <<< "$ARCHITECTURES_RAW"
[[ ${#ARCHITECTURES[@]} -gt 0 ]] || { echo "No frontend architecture selected." >&2; exit 1; }
for arch in "${ARCHITECTURES[@]}"; do
    case "$arch" in
        arm64|x86_64) ;;
        *) echo "Unsupported frontend architecture: $arch" >&2; exit 1 ;;
    esac
done

DIST="${ROOT}/dist"
APP="${DIST}/${APP_NAME}.app"
CONTENTS="${APP}/Contents"
BACKEND="${CONTENTS}/Resources/Backend"
LOCALIZATION_ROOT="${ROOT}/Resources/Localization"

if [[ "$REQUIRES_LLDB" == "1" ]]; then
    LLDB="$(xcrun --find lldb 2>/dev/null || true)"
    [[ -n "$LLDB" ]] || { echo "The active game module requires LLDB." >&2; exit 1; }
    if ! /usr/bin/xcrun python3 -c 'import subprocess,sys; p=subprocess.check_output(["/usr/bin/xcrun","lldb","-P"], text=True).strip(); assert p; sys.path.insert(0,p); import lldb; assert lldb.SBDebugger' >/dev/null 2>&1; then
        DEVELOPER_PATH="$(xcode-select -p 2>/dev/null || true)"
        echo "The active game module requires LLDB Python, but the selected developer environment cannot load it." >&2
        echo "Selected developer directory: ${DEVELOPER_PATH:-unknown}" >&2
        if [[ "$DEVELOPER_PATH" == *"CommandLineTools"* ]]; then
            echo "The selected module requires LLDB Python from a full Xcode installation; Command Line Tools alone are insufficient on this machine." >&2
        fi
        echo "Select full Xcode with: sudo xcode-select -s /Applications/Xcode.app/Contents/Developer" >&2
        echo "Then verify: xcrun lldb -P" >&2
        exit 1
    fi
fi

GENERATED_SWIFT="$GENERATED_DIR/ActiveGame.generated.swift"
"$PYTHON" "$BINDING_GENERATOR" "$ACTIVE_GAME_ID" "$GENERATED_SWIFT"
grep -q "typealias ActiveGameModule = ${FRONTEND_MODULE_TYPE}" "$GENERATED_SWIFT" || {
    echo "Generated active game binding is invalid." >&2; exit 1;
}

rm -rf "$APP"
mkdir -p "${CONTENTS}/MacOS" "$BACKEND" "${CONTENTS}/Resources"
cp "$ROOT/Info.plist" "${CONTENTS}/Info.plist"
for language in en zh-CN; do
    source="${LOCALIZATION_ROOT}/${language}.lproj/Host.strings"
    [[ -f "$source" ]] || { echo "Missing Host localization table: $source" >&2; exit 1; }
    destination="${CONTENTS}/Resources/${language}.lproj"
    mkdir -p "$destination"
    cp "$source" "${destination}/Host.strings"
done
"$PYTHON" - "$LOCALIZATION_ROOT" "${CONTENTS}/Resources" <<'PY'
import sys
from pathlib import Path

source_root, resources = map(Path, sys.argv[1:])
for language in ("en", "zh-CN"):
    source = source_root / f"{language}.lproj/Host.strings"
    packaged = resources / f"{language}.lproj/Host.strings"
    if not packaged.is_file() or packaged.read_bytes() != source.read_bytes():
        raise SystemExit(f"Host localization package mismatch: {packaged}")
PY

SWIFT_SOURCES=("$ROOT/Sources/App.swift")
while IFS= read -r file; do SWIFT_SOURCES+=("$file"); done < <(find "$ROOT/Sources/Core" -type f -name '*.swift' | sort)
while IFS= read -r file; do SWIFT_SOURCES+=("$file"); done < <(find "$FRONTEND_DIR" -type f -name '*.swift' | sort)
SWIFT_SOURCES+=("$GENERATED_SWIFT")
[[ ${#SWIFT_SOURCES[@]} -gt 3 ]] || { echo "No usable Swift sources for $ACTIVE_GAME_ID." >&2; exit 1; }

ARCH_BINARIES=()
for arch in "${ARCHITECTURES[@]}"; do
    binary="$GENERATED_DIR/$EXECUTABLE.$arch"

    # Semantic preflight catches cross-file access/type errors before the
    # optimized compiler path, where SwiftUI failures can otherwise crash with
    # an unhelpful constraint-solver stack dump.
    "$SWIFTC" \
        -typecheck \
        -parse-as-library \
        -target "${arch}-apple-macosx${MIN_MACOS}" \
        -sdk "$SDK" \
        -framework SwiftUI \
        -framework AppKit \
        -framework Carbon \
        "${SWIFT_SOURCES[@]}"

    "$SWIFTC" \
        -parse-as-library \
        -O \
        -target "${arch}-apple-macosx${MIN_MACOS}" \
        -sdk "$SDK" \
        -framework SwiftUI \
        -framework AppKit \
        -framework Carbon \
        "${SWIFT_SOURCES[@]}" \
        -o "$binary"
    ARCH_BINARIES+=("$binary")
done

if [[ ${#ARCH_BINARIES[@]} -eq 1 ]]; then
    cp "${ARCH_BINARIES[0]}" "${CONTENTS}/MacOS/${EXECUTABLE}"
else
    LIPO="$(xcrun --find lipo 2>/dev/null || true)"
    [[ -n "$LIPO" ]] || { echo "Universal build requested but lipo is unavailable." >&2; exit 1; }
    "$LIPO" -create "${ARCH_BINARIES[@]}" -output "${CONTENTS}/MacOS/${EXECUTABLE}"
fi

# Package generic backend core + only the selected game module.
cp -R "$ROOT/Backend/core" "$BACKEND/core"
mkdir -p "$BACKEND/games"
cp "$ROOT/Backend/games/__init__.py" "$BACKEND/games/__init__.py"
cp -R "$ROOT/Backend/games/$ACTIVE_GAME_ID" "$BACKEND/games/$ACTIVE_GAME_ID"

TIME_WARP_ROOT="$ROOT/Native/ProcessTimeWarp"
TIME_WARP_SOURCE="$TIME_WARP_ROOT/ProcessTimeWarp.c"
TIME_WARP_FISHHOOK="$TIME_WARP_ROOT/vendor/fishhook/fishhook.c"
TIME_WARP_NATIVE_DIR="$BACKEND/core/native"
TIME_WARP_DYLIB="$TIME_WARP_NATIVE_DIR/libMGTTimeWarp.dylib"
[[ -f "$TIME_WARP_SOURCE" && -f "$TIME_WARP_FISHHOOK" ]] || {
    echo "Missing Process Time Warp native sources." >&2
    exit 1
}
mkdir -p "$TIME_WARP_NATIVE_DIR"
TIME_WARP_ARCH_BINARIES=()
for arch in "${ARCHITECTURES[@]}"; do
    helper="$GENERATED_DIR/libMGTTimeWarp.$arch.dylib"
    # Production Process Time Warp + bundled fishhook compile. Keep warnings visible
    # without making pre-existing/vendor diagnostics a new build-failure gate.
    "$CLANG" \
        -dynamiclib \
        -isysroot "$SDK" \
        -arch "$arch" \
        -mmacosx-version-min="$MIN_MACOS" \
        -std=c11 \
        -Wall \
        -Wextra \
        -Os \
        -fvisibility=hidden \
        -I"$TIME_WARP_ROOT/vendor/fishhook" \
        "$TIME_WARP_SOURCE" "$TIME_WARP_FISHHOOK" \
        -framework QuartzCore \
        -o "$helper"
    TIME_WARP_ARCH_BINARIES+=("$helper")
done
if [[ ${#TIME_WARP_ARCH_BINARIES[@]} -eq 1 ]]; then
    cp "${TIME_WARP_ARCH_BINARIES[0]}" "$TIME_WARP_DYLIB"
else
    TIME_WARP_LIPO="$(xcrun --find lipo 2>/dev/null || true)"
    [[ -n "$TIME_WARP_LIPO" ]] || { echo "Universal Time Warp helper requested but lipo is unavailable." >&2; exit 1; }
    "$TIME_WARP_LIPO" -create "${TIME_WARP_ARCH_BINARIES[@]}" -output "$TIME_WARP_DYLIB"
fi
codesign --force --sign - --timestamp=none "$TIME_WARP_DYLIB"
codesign --verify --strict "$TIME_WARP_DYLIB"
cp "$TIME_WARP_ROOT/vendor/fishhook/LICENSE" "$TIME_WARP_NATIVE_DIR/LICENSE.fishhook"

find "$BACKEND" -name '__pycache__' -type d -prune -exec rm -rf {} +
printf '%s\n' "$ACTIVE_GAME_ID" > "${CONTENTS}/Resources/ACTIVE_GAME_ID"

HAS_ICON=0
if [[ -f "$ROOT/AppIcon.icns" ]]; then
    cp "$ROOT/AppIcon.icns" "${CONTENTS}/Resources/AppIcon.icns"
    HAS_ICON=1
fi

"$PYTHON" - "${CONTENTS}/Info.plist" "$APP_BUNDLE_ID" "$APP_NAME" "$MIN_MACOS" "$HAS_ICON" "${ARCHITECTURES[@]}" <<'PY'
import plistlib, sys
from pathlib import Path
path = Path(sys.argv[1])
bundle_id, app_name, minimum_macos = sys.argv[2:5]
has_icon = sys.argv[5] == '1'
architectures = sys.argv[6:]
with path.open('rb') as stream:
    data = plistlib.load(stream)
data['CFBundleIdentifier'] = bundle_id
data['CFBundleName'] = app_name
data['CFBundleDisplayName'] = app_name
data['LSMinimumSystemVersion'] = minimum_macos
data['LSArchitecturePriority'] = architectures
if has_icon:
    data['CFBundleIconFile'] = 'AppIcon'
else:
    data.pop('CFBundleIconFile', None)
with path.open('wb') as stream:
    plistlib.dump(data, stream, sort_keys=False)
PY

chmod 755 "${CONTENTS}/MacOS/${EXECUTABLE}"
find "$BACKEND" -type f -exec chmod 644 {} +
chmod 644 "${CONTENTS}/Info.plist"
plutil -lint "${CONTENTS}/Info.plist" >/dev/null

if [[ -n "$ENTITLEMENTS_REL" ]]; then
    ENTITLEMENTS="$ROOT/$ENTITLEMENTS_REL"
    [[ -f "$ENTITLEMENTS" ]] || { echo "Missing module entitlements: $ENTITLEMENTS" >&2; exit 1; }
    codesign --force --sign - --entitlements "$ENTITLEMENTS" --timestamp=none "$APP"
else
    codesign --force --sign - --timestamp=none "$APP"
fi
codesign --verify --deep --strict "$APP"

if [[ "$REQUIRES_DEBUGGER_ENTITLEMENT" == "1" ]]; then
    SIGN_INFO="$(codesign -d --entitlements :- "$APP" 2>&1 || true)"
    if ! printf '%s' "$SIGN_INFO" | grep -q 'com.apple.security.cs.debugger'; then
        echo "The active game module requires com.apple.security.cs.debugger, but the built app does not have it." >&2
        exit 1
    fi
fi

cat <<MSG
Built:
  $APP
Game module:
  $ACTIVE_GAME_ID
Architectures:
  ${ARCHITECTURES[*]}

Launch with Finder or:
  open "$APP"
MSG
