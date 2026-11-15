"""Hosted macOS outer watchdog budgets for Hades II view and model flow journeys."""

JOURNEY_BUDGETS: dict[str, float] = {
    # Hades II native journeys (tests/test_hades2_view_state_flow.py & test_hades2_model_flow.py).
    # Shares exerciseVisualHierarchy and exerciseRoomPickerAlignment with Hades I.
    "hades2.hierarchy": 30.0,
    "hades2.slider": 20.0,
    "hades2.disclosure": 60.0,
    "hades2.search": 20.0,
    "hades2.state_flow": 30.0,
    "hades2.world_exit": 30.0,
    "hades2.live_trait_flow": 30.0,
}
