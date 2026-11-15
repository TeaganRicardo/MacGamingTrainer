"""Hosted macOS outer watchdog budgets for Hades II panel and log-watcher journeys."""

JOURNEY_BUDGETS: dict[str, float] = {
    "native.hades2_run_log_watcher": 20.0,
    "native.hades2_force_enable_rerolls_frontend": 30.0,
    "native.hades2_gathering_frontend": 30.0,
    "native.hades2_chaos_gate_frontend": 30.0,
    "native.hades2_repeated_actions_frontend": 30.0,
}
