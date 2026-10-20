#!/usr/bin/env bash
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if ! cd "$ROOT"; then
  echo "ERROR: cannot enter repository root: $ROOT" >&2
  exit 2
fi

failures=()
record_failure() {
  failures+=("$1")
  printf 'FAIL: %s\n' "$1" >&2
}

run_check() {
  local label="$1"
  shift
  printf '==> %s\n' "$label"
  if "$@"; then
    printf 'PASS: %s\n' "$label"
  else
    local status=$?
    record_failure "$label (exit $status)"
  fi
}

# Tests build fixtures with tempfile.mkdtemp and some production defaults derive
# storage from HOME. Keep both temporary files and accidental default-path
# writes inside one private tree owned by the lane.
if ! LANE_TMP="$(mktemp -d "${TMPDIR:-/tmp}/mgt-lane-XXXXXX")"; then
  echo "ERROR: could not create isolated test directory" >&2
  exit 2
fi
cleanup_lane_tmp() {
  if [[ -n "${LANE_TMP:-}" && -d "${LANE_TMP:-}" && "${LANE_TMP}" == */mgt-lane-* ]]; then
    rm -rf -- "$LANE_TMP"
  fi
  return 0
}
trap cleanup_lane_tmp EXIT
export TMPDIR="$LANE_TMP"
export HOME="$LANE_TMP/home"
if ! mkdir -p "$HOME"; then
  record_failure "create isolated HOME"
fi

MACOS_ONLY_LIST="$ROOT/Tools/macos_only_tests.txt"
if [[ -f "$MACOS_ONLY_LIST" ]]; then
  while IFS= read -r name || [[ -n "$name" ]]; do
    [[ -n "$name" ]] || continue
    test_file="$ROOT/tests/$name"
    if [[ ! -f "$test_file" ]]; then
      record_failure "missing macOS-only test: $name"
      continue
    fi
    run_check "$name" python3 "$test_file"
  done < "$MACOS_ONLY_LIST"
else
  record_failure "missing macOS-only test list: $MACOS_ONLY_LIST"
fi

if (("${#failures[@]}" > 0)); then
  printf '\nmacOS contract suite failed in %d check(s):\n' "${#failures[@]}" >&2
  printf ' - %s\n' "${failures[@]}" >&2
  exit 1
fi

echo "macos_checks_ok"
