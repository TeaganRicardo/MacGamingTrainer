#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

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
