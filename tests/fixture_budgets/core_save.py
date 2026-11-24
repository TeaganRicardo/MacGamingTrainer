"""Hosted macOS outer watchdog budgets for shared Core Save manager journeys."""

JOURNEY_BUDGETS: dict[str, float] = {
    "native.core_save_batch_delete_round20": 20.0,
    "native.core_save_rename_completion_round24": 20.0,
    "native.core_save_manager_lifecycle_u01_u02.1": 20.0,
    "native.core_save_manager_lifecycle_u01_u02.2": 20.0,
    "native.core_save_retention_controls": 45.0,
    "native.core_generic_save_editor": 45.0,
}
