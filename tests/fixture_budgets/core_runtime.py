"""Hosted macOS outer watchdog budgets for shared Core runtime and host journeys."""

JOURNEY_BUDGETS: dict[str, float] = {
    "native.trainer_log_session_lifecycle": 30.0,
    "native.backend_stderr_liveness": 20.0,
    "native.host_target_ownership": 20.0,
}
