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

# Linux collects paths recursively; the shared macOS-only list is the sole
# exclusion source, so new portable tests cannot miss the gate.
discovered_tests="$(python3 Tools/discover_linux_tests.py --root "$ROOT")"
while IFS= read -r test_file; do
  [[ -n "$test_file" ]] || continue
  echo "==> $test_file"
  python3 "$test_file"
done <<< "$discovered_tests"

echo "linux_checks_ok"
