#!/usr/bin/env bash
set -euo pipefail

python3 -m compileall -q Backend
python3 Tools/validate_game_module.py hades2

tests=(
  tests/test_backend_core_round12.py
  tests/test_boundary_performance_ledger_v0180.py
  tests/test_catalog_naming.py
  tests/test_connect_phase_profile.py
  tests/test_corrupt_file_quarantine_v0180.py
  tests/test_hades2_adapter_round12.py
  tests/test_hades2_timeout_policy_v0177.py
  tests/test_localization_cache_recovery_v0180.py
  tests/test_module_contract_round13.py
  tests/test_packaged_module_round14.py
  tests/test_cross_game_isolation.py
  tests/test_passive_ready_transition.py
  tests/test_persistence_integrity_v0180.py
  tests/test_post_v01_feature_contracts.py
  tests/test_preference_commit_efficiency_dev8.py
  tests/test_preferences_schema_v0180.py
  tests/test_profile_envelope_contract_v0180.py
  tests/test_profile_shortcut_schema_v0180.py
  tests/test_protocol_fixtures_v0180.py
  tests/test_reward_naming_audit.py
  tests/test_schema_versioning_v0180.py
)

for test_file in "${tests[@]}"; do
  echo "==> $test_file"
  python3 "$test_file"
done

echo "linux_checks_ok"
