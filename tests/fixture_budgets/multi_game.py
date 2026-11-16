"""Hosted macOS outer watchdog budgets for multi-game and reference-fixture journeys."""

JOURNEY_BUDGETS: dict[str, float] = {
    "reference_fixture.suffix_identity": 30.0,
    "native.reference_fixture_session_integration": 45.0,
    "multi_game_navigation.startup": 30.0,
    "multi_game_navigation.journey": 45.0,
    "multi_game.context_state": 90.0,
    "multi_game.context_navigation": 90.0,
    "multi_game.cross_module_geometry": 60.0,
}
