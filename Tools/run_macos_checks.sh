#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

python3 -m compileall -q Backend
python3 Tools/validate_game_module.py hades2

for test_file in "$ROOT"/tests/test_*.py; do
    echo "==> $test_file"
    python3 "$test_file"
done

echo "macos_checks_ok"
