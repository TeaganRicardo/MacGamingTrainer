#!/usr/bin/env bash
# Run every portable test. Tests get a private HOME and TMPDIR so nothing can
# reach real saves or ~/Library. Only git-tracked tests run.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 2

LANE_TMP="$(mktemp -d "${TMPDIR:-/tmp}/mgt-lane-XXXXXX")" || exit 2
trap 'rm -rf -- "$LANE_TMP"' EXIT
export TMPDIR="$LANE_TMP" HOME="$LANE_TMP/home"
mkdir -p "$HOME" || exit 2

failures=()
run() { echo "==> $1"; if "${@:2}"; then echo "PASS: $1"; else failures+=("$1"); echo "FAIL: $1" >&2; fi; }

tests="$(git ls-files 'tests/test_*.py')" && [ -n "$tests" ] || { echo "ERROR: no tracked tests found" >&2; exit 2; }
run "Compile backend" python3 -m compileall -q Backend
run "Validate game modules" python3 Tools/validate_game_module.py --all
for test in $tests; do
  grep -q '^MGT_PLATFORM = "macos"' "$test" || run "$test" python3 "$test"
done

if ((${#failures[@]})); then printf 'FAILED: %s\n' "${failures[@]}" >&2; exit 1; fi
echo "linux_checks_ok"
