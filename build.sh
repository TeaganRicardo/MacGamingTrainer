#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
MODULE_VALIDATOR="${ROOT}/Tools/validate_game_module.py"
BINDING_GENERATOR="${ROOT}/Tools/generate_game_binding.py"

for tool in xcrun xcode-select codesign plutil grep find uname xattr curl shasum tar file; do
    command -v "$tool" >/dev/null 2>&1 || { echo "Missing required tool: $tool" >&2; exit 1; }
done

SDK="$(xcrun --sdk macosx --show-sdk-path)"
SWIFTC="$(xcrun --find swiftc)"
CLANG="$(xcrun --find clang 2>/dev/null || true)"
[[ -n "$CLANG" ]] || { echo "Xcode developer tools must provide clang." >&2; exit 1; }
[[ -x "$MODULE_VALIDATOR" && -x "$BINDING_GENERATOR" ]] || { echo "Missing game module build tools under Tools/." >&2; exit 1; }
PYTHON_RUNTIME_MANIFEST="${ROOT}/Tools/python_runtime.json"
[[ -f "$PYTHON_RUNTIME_MANIFEST" ]] || { echo "Missing pinned Python runtime manifest: $PYTHON_RUNTIME_MANIFEST" >&2; exit 1; }
CLEAN_SIGNING_METADATA="${ROOT}/Tools/clean_signing_metadata.py"
PACKAGE_APP="${ROOT}/Tools/package_app.py"
[[ -f "$CLEAN_SIGNING_METADATA" && -f "$PACKAGE_APP" ]] || { echo "Missing packaging tools under Tools/." >&2; exit 1; }

# --typecheck uses the same product metadata and Swift compiler preflight as
# the distributable build, but never downloads/copies bundled Python, emits a
# binary, signs, or publishes a package. It is not release verification.
BUILD_MODE=full
if [[ "${1:-}" == "--typecheck" ]]; then
    BUILD_MODE=typecheck
    shift
fi
# Build selection is explicit and independent from MGT_GAME_ID, which is a
# runtime environment value for the backend worker. A bare build is the product.
BUILD_SELECTION="${1:-all}"
[[ "$BUILD_SELECTION" != "--all" ]] || BUILD_SELECTION="all"
if [[ $# -gt 1 || "$BUILD_SELECTION" == --* ]]; then
    echo "Usage: ./build.sh [--typecheck] [--all|game-id]" >&2
    exit 2
fi

BUILD_STARTED_SECONDS=$SECONDS
PHASE_STARTED_SECONDS=$SECONDS
record_build_timing() {
    local elapsed=$((SECONDS - PHASE_STARTED_SECONDS))
    printf 'MGT_BUILD_TIMING mode=%s selection=%s phase=%s seconds=%d total=%d\n' \
        "$BUILD_MODE" "$BUILD_SELECTION" "$1" "$elapsed" "$((SECONDS - BUILD_STARTED_SECONDS))"
    PHASE_STARTED_SECONDS=$SECONDS
}

GENERATED_DIR="$(mktemp -d "${TMPDIR:-/tmp}/mgt-build.XXXXXX")"
trap 'rm -rf "$GENERATED_DIR"' EXIT

python_runtime_field() {
    plutil -extract "$1" raw -o - "$PYTHON_RUNTIME_MANIFEST"
}

prepare_python_runtime() (
    set -e
    # Subshell scope keeps temporary visible to the EXIT trap after function return.
    temporary=""
    trap 'if [[ -n "$temporary" ]]; then rm -f "$temporary"; fi' EXIT
    local arch="$1"
    local destination="$GENERATED_DIR/python-runtime/$arch"
    local runtime="$destination/python"
    if [[ -x "$runtime/bin/python3" ]]; then
        printf '%s\n' "$runtime"
        return
    fi

    local version release url sha cache_root archive actual runtime_arches
    version="$(python_runtime_field version)"
    release="$(python_runtime_field release)"
    url="$(python_runtime_field "distributions.$arch.url")"
    sha="$(python_runtime_field "distributions.$arch.sha256")"
    [[ -n "$version" && -n "$release" && -n "$url" && "$sha" =~ ^[0-9a-f]{64}$ ]] || {
        echo "Invalid Python runtime declaration for $arch." >&2
        exit 1
    }

    cache_root="${MGT_PYTHON_RUNTIME_CACHE_DIR:-${HOME:-${TMPDIR:-/tmp}}/Library/Caches/MacGamingTrainer/python-runtime}"
    mkdir -p "$cache_root"
    archive="$cache_root/cpython-${version}+${release}-${arch}-apple-darwin-install_only.tar.gz"
    if [[ ! -f "$archive" ]] || ! printf '%s  %s\n' "$sha" "$archive" | shasum -a 256 -c - >/dev/null 2>&1; then
        temporary="$(mktemp "$archive.tmp.XXXXXX")"
        curl -fL --retry 3 --retry-delay 1 -o "$temporary" "$url"
        printf '%s  %s\n' "$sha" "$temporary" | shasum -a 256 -c - >/dev/null
        mv "$temporary" "$archive"
    fi

    mkdir -p "$destination"
    tar -xzf "$archive" -C "$destination"
    [[ -x "$runtime/bin/python3" ]] || {
        echo "Pinned Python runtime is missing bin/python3 for $arch." >&2
        exit 1
    }
    if [[ "$arch" == "$(uname -m)" ]]; then
        actual="$("$runtime/bin/python3" -c 'import platform; print(platform.python_version())')"
        [[ "$actual" == "$version" ]] || {
            echo "Pinned Python runtime version mismatch for $arch: expected $version, got $actual." >&2
            exit 1
        }
    elif [[ "$(uname -s)" == "Darwin" ]]; then
        # The archive checksum above authenticates the pinned runtime version.
        # A cross-architecture macOS build host cannot execute the target
        # interpreter, so validate the Mach-O architecture without launching it.
        # Portable non-Darwin bootstrap tests rely on the same per-arch checksum.
        runtime_arches="$(xcrun lipo -archs "$runtime/bin/python3")" || {
            echo "Pinned Python runtime is not a valid Mach-O executable for $arch." >&2
            exit 1
        }
        case " $runtime_arches " in
            *" $arch "*) ;;
            *)
                echo "Pinned Python runtime architecture mismatch for $arch: got $runtime_arches." >&2
                exit 1
                ;;
        esac
    fi
    printf '%s\n' "$runtime"
)

HOST_ARCH="$(uname -m)"
case "$HOST_ARCH" in
    arm64|x86_64) ;;
    *) echo "Unsupported build-host architecture for bundled Python: $HOST_ARCH" >&2; exit 1 ;;
esac
if [[ "$BUILD_MODE" == "typecheck" ]]; then
    # The hosted workflow pins this interpreter to Tools/python_runtime.json.
    # A Swift-only preflight does not need a bundled cross-architecture runtime.
    PYTHON="$(command -v python3)" || { echo "Missing python3 for typecheck." >&2; exit 1; }
else
    HOST_PYTHON_ROOT="$(prepare_python_runtime "$HOST_ARCH")"
    PYTHON="$HOST_PYTHON_ROOT/bin/python3"
fi

NORMALIZED_MANIFEST="$GENERATED_DIR/module.normalized.json"
"$PYTHON" "$ROOT/Tools/product_support.py" "$BUILD_SELECTION" > "$NORMALIZED_MANIFEST"

manifest_field() {
    "$PYTHON" "$PACKAGE_APP" manifest-field "$NORMALIZED_MANIFEST" "$1"
}

read -r -a GAME_IDS <<< "$(manifest_field moduleIDs)"
SELECTION_ID="$(manifest_field id)"
ACTIVE_GAME_ID="$SELECTION_ID"
GAME_SELECTION_CSV="$(IFS=,; echo "${GAME_IDS[*]}")"
ARCHITECTURES_RAW="$(manifest_field frontend.architectures)"
MIN_MACOS="$(manifest_field frontend.minimumMacOS)"
APP_BUNDLE_ID="$(manifest_field app.bundleIdentifier)"
APP_NAME="$(manifest_field app.displayName)"
EXECUTABLE="$(manifest_field app.executable)"
REQUIRES_LLDB="$(manifest_field buildRequirements.lldbPython)"
REQUIRES_DEBUGGER_ENTITLEMENT="$(manifest_field buildRequirements.debuggerEntitlement)"
ENTITLEMENTS_REL="$(manifest_field buildRequirements.entitlements)"

[[ -n "$APP_NAME" && "$APP_NAME" != *'/'* ]] || { echo "Invalid app display name from module manifest." >&2; exit 1; }
[[ -n "$APP_BUNDLE_ID" ]] || { echo "Missing app bundle identifier." >&2; exit 1; }
read -r -a ARCHITECTURES <<< "$ARCHITECTURES_RAW"
[[ ${#ARCHITECTURES[@]} -gt 0 ]] || { echo "No frontend architecture selected." >&2; exit 1; }
for arch in "${ARCHITECTURES[@]}"; do
    case "$arch" in
        arm64|x86_64) ;;
        *) echo "Unsupported frontend architecture: $arch" >&2; exit 1 ;;
    esac
    if [[ "$BUILD_MODE" == "full" ]]; then
        prepare_python_runtime "$arch" >/dev/null
    fi
done
record_build_timing "runtime-bootstrap"

DIST="${GENERATED_DIR}/dist"
PUBLISH_DIST="${MGT_BUILD_OUTPUT_DIR:-${ROOT}/dist}"
APP="${DIST}/${APP_NAME}.app"
PUBLISH_APP="${PUBLISH_DIST}/${APP_NAME}.app"
[[ ! -L "$PUBLISH_DIST" ]] || { echo "Build output dist must not be a symlink: $PUBLISH_DIST" >&2; exit 1; }
CONTENTS="${APP}/Contents"
BACKEND="${CONTENTS}/Resources/Backend"
LOCALIZATION_ROOT="${ROOT}/Resources/Localization"

if [[ "$BUILD_MODE" == "full" && "$REQUIRES_LLDB" == "1" ]]; then
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

# The App, Core and each selected game compile as separate Swift modules of one
# package. Each module sees only the swiftmodules of its declared dependencies,
# so Core cannot import a game and a game cannot import another game.
SWIFT_PACKAGE_NAME="$(manifest_field frontend.swift.packageName)"
[[ -n "$SWIFT_PACKAGE_NAME" ]] || { echo "Missing Swift package name." >&2; exit 1; }
GENERATED_SWIFT_DIR="$GENERATED_DIR/swift-generated"
SWIFT_SOURCE_LISTS="$GENERATED_DIR/swift-sources"
SWIFT_MODULE_ORDER="$GENERATED_DIR/swift-modules.tsv"
SWIFT_BUILD_DIR="$GENERATED_DIR/swift-build"
"$PYTHON" "$BINDING_GENERATOR" "$GAME_SELECTION_CSV" --module-sources "$GENERATED_SWIFT_DIR"
"$PYTHON" "$PACKAGE_APP" prepare-swift-inputs "$NORMALIZED_MANIFEST" "$ROOT" "$GENERATED_SWIFT_DIR" "$SWIFT_SOURCE_LISTS" > "$SWIFT_MODULE_ORDER"
grep -q "enum TrainerGameCatalog" "$GENERATED_SWIFT_DIR"/*/TrainerGameCatalog.generated.swift || {
    echo "Generated game catalog is invalid." >&2; exit 1;
}

record_build_timing "product-frontend-inputs"

# compile_swift_modules MODE ARCH [BINARY]
# typecheck: emit each library module's interface and typecheck the App.
# optimized: build each library module as a static archive and link the App.
compile_swift_modules() {
    local mode="$1" arch="$2" binary="${3:-}"
    local modules_root="$SWIFT_BUILD_DIR/$mode/$arch"
    local name role dependencies dependency file module_dir
    local archives=()
    while IFS=$'\t' read -r name role dependencies; do
        module_dir="$modules_root/$name"
        mkdir -p "$module_dir"
        local arguments=(
            -parse-as-library
            -target "${arch}-apple-macosx${MIN_MACOS}"
            -sdk "$SDK"
            -module-name "$name"
            -package-name "$SWIFT_PACKAGE_NAME"
        )
        if [[ "$mode" == "typecheck" ]]; then
            arguments+=(-strict-concurrency=targeted -warnings-as-errors)
        fi
        local search_paths=()
        IFS=',' read -r -a search_paths <<< "$dependencies"
        for dependency in ${search_paths[@]+"${search_paths[@]}"}; do
            arguments+=(-I "$modules_root/$dependency")
        done
        local sources=()
        while IFS= read -r file; do sources+=("$file"); done < "$SWIFT_SOURCE_LISTS/$name.txt"
        if [[ "$role" == "app" && "$mode" == "typecheck" ]]; then
            "$SWIFTC" -typecheck "${arguments[@]}" "${sources[@]}"
        elif [[ "$role" == "app" ]]; then
            "$SWIFTC" -O "${arguments[@]}" \
                -framework SwiftUI -framework AppKit -framework Carbon \
                "${sources[@]}" ${archives[@]+"${archives[@]}"} -o "$binary"
        elif [[ "$mode" == "typecheck" ]]; then
            "$SWIFTC" -emit-module -emit-module-path "$module_dir/$name.swiftmodule" \
                "${arguments[@]}" "${sources[@]}"
        else
            "$SWIFTC" -O -emit-module -emit-module-path "$module_dir/$name.swiftmodule" \
                -emit-library -static -o "$module_dir/lib$name.a" \
                "${arguments[@]}" "${sources[@]}"
            # Load every object so runtime conformance lookup sees the whole module.
            archives+=(-Xlinker -force_load -Xlinker "$module_dir/lib$name.a")
        fi
    done < "$SWIFT_MODULE_ORDER"
}

# Compiler preflight is shared by normal builds and the lightweight PR path.
for arch in "${ARCHITECTURES[@]}"; do
    # Semantic preflight catches cross-file access/type errors before the
    # optimized compiler path, where SwiftUI failures can otherwise crash with
    # an unhelpful constraint-solver stack dump.
    compile_swift_modules typecheck "$arch"
done
record_build_timing "swift-typecheck"

if [[ "$BUILD_MODE" == "typecheck" ]]; then
    printf 'Validated Swift product catalog and typechecked %s for %s (%s).\n' \
        "$APP_NAME" "$BUILD_SELECTION" "${ARCHITECTURES[*]}"
    exit 0
fi

rm -rf "$APP"
mkdir -p "${CONTENTS}/MacOS" "$BACKEND" "${CONTENTS}/Resources"
cp "$ROOT/Info.plist" "${CONTENTS}/Info.plist"

PYTHON_RESOURCES="${CONTENTS}/Resources/Python"
mkdir -p "$PYTHON_RESOURCES"
for arch in "${ARCHITECTURES[@]}"; do
    runtime_root="$GENERATED_DIR/python-runtime/$arch/python"
    destination="$PYTHON_RESOURCES/$arch"
    mkdir -p "$destination"
    cp -R "$runtime_root/." "$destination/"
done
"$PYTHON" "$PACKAGE_APP" write-runtime-metadata "$PYTHON_RUNTIME_MANIFEST" "$PYTHON_RESOURCES/runtime.json" "${ARCHITECTURES[@]}"
for language in en zh-CN; do
    source="${LOCALIZATION_ROOT}/${language}.lproj/Host.strings"
    [[ -f "$source" ]] || { echo "Missing Host localization table: $source" >&2; exit 1; }
    destination="${CONTENTS}/Resources/${language}.lproj"
    mkdir -p "$destination"
    cp "$source" "${destination}/Host.strings"
done
"$PYTHON" "$PACKAGE_APP" verify-host-localization "$LOCALIZATION_ROOT" "${CONTENTS}/Resources"

# The product purple is the application accent color. AppKit resolves popup
# indicators, menu selection, focus rings and other native accent chrome from
# NSAccentColorName, so a native control redrawn outside a SwiftUI update (for
# example after a system appearance change) keeps the product accent instead of
# falling back to the system blue.
ASSET_CATALOG="${ROOT}/Resources/Assets.xcassets"
ACCENT_COLOR_NAME="AccentColor"
[[ -f "${ASSET_CATALOG}/${ACCENT_COLOR_NAME}.colorset/Contents.json" ]] || {
    echo "Missing application accent color: ${ASSET_CATALOG}/${ACCENT_COLOR_NAME}.colorset" >&2; exit 1;
}
ACTOOL="$(xcrun --find actool 2>/dev/null || true)"
[[ -n "$ACTOOL" ]] || { echo "Xcode developer tools must provide actool." >&2; exit 1; }
ASSET_INFO_PLIST="$GENERATED_DIR/asset-catalog-info.plist"
"$ACTOOL" "$ASSET_CATALOG" \
    --compile "${CONTENTS}/Resources" \
    --platform macosx \
    --minimum-deployment-target "$MIN_MACOS" \
    --accent-color "$ACCENT_COLOR_NAME" \
    --output-partial-info-plist "$ASSET_INFO_PLIST" \
    --errors --warnings --output-format human-readable-text
[[ -f "${CONTENTS}/Resources/Assets.car" ]] || { echo "Asset catalog compilation produced no Assets.car." >&2; exit 1; }
[[ "$(plutil -extract NSAccentColorName raw -o - "$ASSET_INFO_PLIST" 2>/dev/null || true)" == "$ACCENT_COLOR_NAME" ]] || {
    echo "Asset catalog compilation did not declare the application accent color." >&2; exit 1;
}

record_build_timing "package-runtime"

ARCH_BINARIES=()
for arch in "${ARCHITECTURES[@]}"; do
    binary="$GENERATED_DIR/$EXECUTABLE.$arch"
    compile_swift_modules optimized "$arch" "$binary"
    ARCH_BINARIES+=("$binary")
done

if [[ ${#ARCH_BINARIES[@]} -eq 1 ]]; then
    cp "${ARCH_BINARIES[0]}" "${CONTENTS}/MacOS/${EXECUTABLE}"
else
    LIPO="$(xcrun --find lipo 2>/dev/null || true)"
    [[ -n "$LIPO" ]] || { echo "Universal build requested but lipo is unavailable." >&2; exit 1; }
    "$LIPO" -create "${ARCH_BINARIES[@]}" -output "${CONTENTS}/MacOS/${EXECUTABLE}"
fi
record_build_timing "swift-optimized"

# Package generic backend core and the selected game module set. Preserve
# permitted xattrs; clean only FinderInfo/ResourceFork before signing.
cp -R "$ROOT/Backend/core" "$BACKEND/core"
if [[ "$REQUIRES_LLDB" == "1" ]]; then
    cp -R "$ROOT/Backend/debugger" "$BACKEND/debugger"
fi
mkdir -p "$BACKEND/games"
cp "$ROOT/Backend/games/__init__.py" "$BACKEND/games/__init__.py"
for game_id in "${GAME_IDS[@]}"; do
    cp -R "$ROOT/Backend/games/$game_id" "$BACKEND/games/$game_id"
done
"$PYTHON" "$PACKAGE_APP" package-app-resources "$NORMALIZED_MANIFEST" "$ROOT" "${CONTENTS}/Resources"

# Construct the packaged adapter with the pinned application Python.
# HOME is isolated so build verification cannot touch developer or runner state.
BACKEND_SMOKE_HOME="$GENERATED_DIR/backend-smoke-home"
mkdir -p "$BACKEND_SMOKE_HOME"
PYTHONPATH="$BACKEND" HOME="$BACKEND_SMOKE_HOME" "$PYTHON" "$PACKAGE_APP" smoke-adapters "$REQUIRES_LLDB" "${GAME_IDS[@]}"

TIME_WARP_ROOT="$ROOT/Native/ProcessTimeWarp"
"$PYTHON" "$ROOT/Tools/build_module_native.py" "$NORMALIZED_MANIFEST" \
    "$TIME_WARP_ROOT" "$GENERATED_DIR" --process-time-warp \
    --output-dir "$BACKEND/core/native" \
    --clean-signing-metadata "$CLEAN_SIGNING_METADATA" --app "$APP" --staging-root "$DIST" \
    --clang "$CLANG" --sdk "$SDK" --minimum-macos "$MIN_MACOS" \
    --architectures "${ARCHITECTURES[@]}"

for game_id in "${GAME_IDS[@]}"; do
    module_manifest="$GENERATED_DIR/$game_id.normalized.json"
    "$PYTHON" "$MODULE_VALIDATOR" "$game_id" --json > "$module_manifest"
    "$PYTHON" "$ROOT/Tools/build_module_native.py" "$module_manifest" \
        "$BACKEND/games/$game_id" "$GENERATED_DIR" \
        --clean-signing-metadata "$CLEAN_SIGNING_METADATA" --app "$APP" --staging-root "$DIST" \
        --clang "$CLANG" --sdk "$SDK" \
        --minimum-macos "$MIN_MACOS" --architectures "${ARCHITECTURES[@]}"
done
"$PYTHON" "$PACKAGE_APP" write-game-modules "$NORMALIZED_MANIFEST" "${CONTENTS}/Resources/GAME_MODULES.json"

find "$BACKEND" -name '__pycache__' -type d -prune -exec rm -rf {} +
printf '%s\n' "$ACTIVE_GAME_ID" > "${CONTENTS}/Resources/ACTIVE_GAME_ID"
record_build_timing "backend-and-native"

HAS_ICON=0
if [[ -f "$ROOT/AppIcon.icns" ]]; then
    cp "$ROOT/AppIcon.icns" "${CONTENTS}/Resources/AppIcon.icns"
    HAS_ICON=1
fi

"$PYTHON" "$PACKAGE_APP" patch-info-plist "${CONTENTS}/Info.plist" "$APP_BUNDLE_ID" "$APP_NAME" "$MIN_MACOS" "$HAS_ICON" "$ASSET_INFO_PLIST" "${ARCHITECTURES[@]}"

chmod 755 "${CONTENTS}/MacOS/${EXECUTABLE}"
find "$BACKEND" -type f -exec chmod 644 {} +
chmod 644 "${CONTENTS}/Info.plist"
plutil -lint "${CONTENTS}/Info.plist" >/dev/null

# Remove only the two attached-data classes that codesign rejects. Keep
# com.apple.provenance and file-provider provenance/fpfs attributes untouched.
"$PYTHON" "$CLEAN_SIGNING_METADATA" "$APP" --staging-root "$DIST"

# The bundled runtime contains nested Mach-O interpreters, libpython and extension
# modules. Sign nested code before signing the outer app bundle.
while IFS= read -r runtime_code; do
    if file "$runtime_code" | grep -q 'Mach-O'; then
        codesign --force --sign - --timestamp=none "$runtime_code"
    fi
done < <(find "$PYTHON_RESOURCES" -type f \( -name 'python3*' -o -name '*.so' -o -name '*.dylib' \) | sort)

if [[ -n "$ENTITLEMENTS_REL" ]]; then
    ENTITLEMENTS="$GENERATED_DIR/product-entitlements.plist"
    "$PYTHON" "$PACKAGE_APP" merge-entitlements "$NORMALIZED_MANIFEST" "$ROOT" "$ENTITLEMENTS"
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

mkdir -p "$PUBLISH_DIST"
[[ ! -L "$PUBLISH_DIST" ]] || { echo "Build output dist must not be a symlink: $PUBLISH_DIST" >&2; exit 1; }
"$PYTHON" "$ROOT/Tools/publish_module_build.py" "$APP" "$PUBLISH_DIST" "$APP_NAME"
"$PYTHON" "$ROOT/Tools/verify_module_build.py" "$BUILD_SELECTION" --dist-dir "$PUBLISH_DIST" >/dev/null
record_build_timing "sign-and-publish"

cat <<MSG
Built:
  $PUBLISH_APP
Game modules:
  ${GAME_IDS[*]}
Architectures:
  ${ARCHITECTURES[*]}

Launch with Finder or:
  open "$PUBLISH_APP"
MSG
