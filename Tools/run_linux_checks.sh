#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

python3 -m compileall -q Backend
python3 Tools/validate_game_module.py hades2

# These entrypoints compile or import AppKit/Darwin-only Swift. Every other
# test_*.py is Linux-portable by default and therefore enters this gate
# automatically when added to the repository.
macos_only_tests=(
  test_core_save_batch_delete_round20.py
  test_core_save_rename_completion_round24.py
  test_hades2_run_log_watcher.py
  test_trainer_log_sink_shared_append.py
)

is_macos_only() {
  local name="$1"
  local candidate
  for candidate in "${macos_only_tests[@]}"; do
    if [[ "$candidate" == "$name" ]]; then
      return 0
    fi
  done
  return 1
}

for test_file in "$ROOT"/tests/test_*.py; do
  name="$(basename "$test_file")"
  if is_macos_only "$name"; then
    echo "==> SKIP macOS-only $test_file"
    continue
  fi
  echo "==> $test_file"
  python3 "$test_file"
done
