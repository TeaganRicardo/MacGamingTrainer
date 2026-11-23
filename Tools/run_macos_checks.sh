#!/usr/bin/env bash
# Run every macOS test (MGT_PLATFORM = "macos"). Tests get a private HOME and
# TMPDIR so nothing can reach real saves or ~/Library. Only git-tracked tests
# run. --skip-foreground leaves out the journeys that need foreground
# activation; they fail on a busy desktop and run on manual CI dispatch.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 2

FOREGROUND="tests/test_hades2_view_state_flow.py tests/test_multi_game_contexts.py tests/test_runtime_text_edit_completion.py"
skip_foreground=false
case "${1:-}" in
  "") ;;
  --skip-foreground) skip_foreground=true ;;
  *) echo "usage: run_macos_checks.sh [--skip-foreground]" >&2; exit 2 ;;
esac

LANE_TMP="$(mktemp -d "${TMPDIR:-/tmp}/mgt-lane-XXXXXX")" || exit 2
trap 'rm -rf -- "$LANE_TMP"' EXIT
export TMPDIR="$LANE_TMP" HOME="$LANE_TMP/home"
mkdir -p "$HOME" || exit 2

tests="$(git ls-files 'tests/test_*.py')" && [ -n "$tests" ] || { echo "ERROR: no tracked tests found" >&2; exit 2; }
failures=()
run() { echo "==> $1"; if "${@:2}"; then echo "PASS: $1"; else failures+=("$1"); echo "FAIL: $1" >&2; fi; }

for test in $tests; do
  grep -q '^MGT_PLATFORM = "macos"' "$test" || continue
  if $skip_foreground && [[ " $FOREGROUND " == *" $test "* ]]; then echo "SKIP (foreground): $test"; continue; fi
  run "$test" python3 "$test"
done

if ((${#failures[@]})); then printf 'FAILED: %s\n' "${failures[@]}" >&2; exit 1; fi
echo "macos_checks_ok"
