#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Tests build fixtures with tempfile.mkdtemp, which never removes the directory
# it creates. Running the lane inside a private TMPDIR keeps every fixture --
# including one a future test forgets to clean up -- inside a tree this script
# owns, and the trap removes that tree when the lane exits.
LANE_TMP="$(mktemp -d "${TMPDIR:-/tmp}/mgt-lane-XXXXXX")"
cleanup_lane_tmp() {
  if [[ -n "${LANE_TMP:-}" && -d "${LANE_TMP:-}" && "${LANE_TMP}" == */mgt-lane-* ]]; then
    rm -rf -- "$LANE_TMP"
  fi
  return 0
}
trap cleanup_lane_tmp EXIT
export TMPDIR="$LANE_TMP"

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
