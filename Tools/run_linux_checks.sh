#!/usr/bin/env bash
set -euo pipefail

python3 -m compileall -q Backend
python3 Tools/validate_game_module.py hades2

# These tests compile or exercise AppKit/Darwin-only Swift code. Every other
# tests/test_*.py entrypoint runs on Linux by default, so a newly added portable
# regression cannot silently miss the fastest CI lane.
platform_only=" test_core_save_batch_delete_round20.py test_core_save_rename_completion_round24.py test_hades2_run_log_watcher.py test_trainer_log_sink_shared_append.py "

for test_file in tests/test_*.py; do
  name="$(basename "$test_file")"
  case "$platform_only" in
    *" $name "*)
      echo "==> SKIP macOS-only $test_file"
      continue
      ;;
  esac
  echo "==> $test_file"
  python3 "$test_file"
done

echo "linux_checks_ok"
