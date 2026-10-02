#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Tests build fixtures with tempfile.mkdtemp and some production defaults derive
# storage from HOME. Keep both temporary files and accidental default-path
# writes inside one private tree owned by the lane.
LANE_TMP="$(mktemp -d "${TMPDIR:-/tmp}/mgt-lane-XXXXXX")"
cleanup_lane_tmp() {
  if [[ -n "${LANE_TMP:-}" && -d "${LANE_TMP:-}" && "${LANE_TMP}" == */mgt-lane-* ]]; then
    rm -rf -- "$LANE_TMP"
  fi
  return 0
}
trap cleanup_lane_tmp EXIT
export TMPDIR="$LANE_TMP"
export HOME="$LANE_TMP/home"
mkdir -p "$HOME"

MACOS_ONLY_LIST="$ROOT/Tools/macos_only_tests.txt"
test -f "$MACOS_ONLY_LIST"

while IFS= read -r name || [[ -n "$name" ]]; do
  [[ -n "$name" ]] || continue
  test -f "$ROOT/tests/$name"
done < "$MACOS_ONLY_LIST"

python3 -m compileall -q Backend
python3 Tools/validate_game_module.py --all

# Linux collects paths recursively; the shared macOS-only list is the sole
# exclusion source, so new portable tests cannot miss the gate.
discovered_tests="$(python3 Tools/discover_linux_tests.py --root "$ROOT")"
while IFS= read -r test_file; do
  [[ -n "$test_file" ]] || continue
  echo "==> $test_file"
  python3 "$test_file"
done <<< "$discovered_tests"

echo "linux_checks_ok"
