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
    test_file="$ROOT/tests/$name"
    test -f "$test_file"
    echo "==> $test_file"
    python3 "$test_file"
done < "$MACOS_ONLY_LIST"

echo "macos_checks_ok"
