#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

MACOS_ONLY_LIST="$ROOT/Tools/macos_only_tests.txt"
test -f "$MACOS_ONLY_LIST"

while IFS= read -r name || [[ -n "$name" ]]; do
  [[ -n "$name" ]] || continue
  test -f "$ROOT/tests/$name"
done < "$MACOS_ONLY_LIST"

python3 -m compileall -q Backend
python3 Tools/validate_game_module.py hades2

# The shared list is the only exclusion source for Linux-portable tests.
# Every other tests/test_*.py entrypoint runs here by default, so a newly added
# portable regression cannot silently miss the fastest CI lane.
for test_file in tests/test_*.py; do
  name="$(basename "$test_file")"
  if grep -Fqx -- "$name" "$MACOS_ONLY_LIST"; then
    echo "==> SKIP macOS-only $test_file"
    continue
  fi
  echo "==> $test_file"
  python3 "$test_file"
done

echo "linux_checks_ok"
