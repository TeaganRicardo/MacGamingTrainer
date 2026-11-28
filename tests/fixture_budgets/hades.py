"""Hosted macOS outer watchdog budgets for Hades I native journeys."""

JOURNEY_BUDGETS: dict[str, float] = {
    # Hades I native journeys (tests/test_hades_frontend.py).
    # Five hosted observations span 40.1s to 54.0s. A gate must clear the
    # observed maximum by at least one observed spread (13.9s), and 65s did not.
    "hades.save_editor": 80.0,
    # Five hosted runs on macos-26/ARM64 span 19.0s to 29.6s. The earlier 30s
    # gate left 0.4s of headroom on a passing run, which is not containment.
    "hades.recovery": 45.0,
    # Same native connection-fault assertions as recovery, now isolated from
    # unrelated AX/control work. Retain the established 45s outer watchdog.
    "hades.interlock": 45.0,
    "hades.management": 30.0,
    "hades.slider": 20.0,
    # Seven hosted runs on macos-26/ARM64 after #717/#719 expanded hierarchy
    # geometry checks span 15.255s to 20.124s (spread 4.869s); 20s expired
    # after hades_visual_hierarchy_ok printed. Give the journey real margin.
    "hades.hierarchy": 30.0,
    "hades.disclosure": 60.0,
    "hades.search": 20.0,
    "hades.save_editor_frontend": 30.0,
    "native.hades_run_log_watcher": 45.0,
}
