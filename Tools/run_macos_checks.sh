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
    printf '%s\tpass\n' "$label" >> "$RESULTS_FILE"
  else
    local status=$?
    printf '%s\tfail\n' "$label" >> "$RESULTS_FILE"
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

RESULTS_FILE="$LANE_TMP/macos-results.tsv"
SELECTED_FILE="$LANE_TMP/macos-selected.txt"
: > "$RESULTS_FILE"
: > "$SELECTED_FILE"

# Journey timings are observation only. A hosted lane points this at a durable
# path so the artifact survives the lane's temporary directory.
if [[ -z "${MGT_FIXTURE_TIMINGS:-}" ]]; then
  MGT_FIXTURE_TIMINGS="$LANE_TMP/macos-fixture-timings.jsonl"
fi
export MGT_FIXTURE_TIMINGS
COVERAGE_OUTPUT="${MGT_MACOS_COVERAGE_OUTPUT:-}"

MACOS_ONLY_LIST="$ROOT/Tools/macos_only_tests.txt"
LANE="convergence"
selected=""
if [[ ! -f "$MACOS_ONLY_LIST" ]]; then
  record_failure "missing macOS-only test list: $MACOS_ONLY_LIST"
elif [[ $# -eq 0 ]]; then
  # Full inventory is reserved for exact-SHA release convergence.
  selected="$(cat "$MACOS_ONLY_LIST")"
elif [[ $# -eq 3 && "$1" == "--pr" ]]; then
  LANE="pr"
  if ! selected="$(python3 Tools/select_macos_pr_tests.py "$2" "$3")"; then
    record_failure "select PR macOS tests"
  fi
else
  record_failure "usage: run_macos_checks.sh [--pr BASE_SHA HEAD_SHA]"
fi

printf '%s\n' "$selected" > "$SELECTED_FILE"

if [[ -n "$selected" ]]; then
  while IFS= read -r name || [[ -n "$name" ]]; do
    [[ -n "$name" ]] || continue
    test_file="$ROOT/tests/$name"
    if [[ ! -f "$test_file" ]]; then
      record_failure "missing macOS-only test: $name"
      continue
    fi
    run_check "$name" python3 "$test_file"
  done <<< "$selected"
fi

# The lane must state what it ran, what it deferred and who verifies the
# deferred work. A coverage contract violation fails closed; a slow journey
# never does.
coverage_args=(--lane "$LANE" --selected "$SELECTED_FILE" --results "$RESULTS_FILE")
if [[ -n "${MGT_FIXTURE_TIMINGS:-}" ]]; then
  coverage_args+=(--timings "$MGT_FIXTURE_TIMINGS")
fi
if [[ -n "$COVERAGE_OUTPUT" ]]; then
  coverage_args+=(--output "$COVERAGE_OUTPUT")
fi
coverage_status=0
python3 Tools/summarize_macos_coverage.py "${coverage_args[@]}" || coverage_status=$?
if (( coverage_status != 0 )); then
  record_failure "macOS coverage summary (exit $coverage_status)"
fi

if (("${#failures[@]}" > 0)); then
  printf '\nmacOS contract suite failed in %d check(s):\n' "${#failures[@]}" >&2
  printf ' - %s\n' "${failures[@]}" >&2
  exit 1
fi

echo "macos_checks_ok"
