"""Authoritative Hades I Host -> backend command metadata and inner/outer budget definitions."""

from __future__ import annotations

from dataclasses import dataclass

from .operation_budgets import (
    CONNECT_COMMAND_TIMEOUT_SECONDS,
    CONNECT_OPERATION_BUDGET_SECONDS,
    DEFAULT_COMMAND_TIMEOUT_SECONDS,
    DEFERRED_TRAIT_COMMAND_TIMEOUT_SECONDS,
    FEATURE_AND_LOCK_COMMAND_TIMEOUT_SECONDS,
    LAUNCH_COMMAND_TIMEOUT_SECONDS,
    LAUNCH_OPERATION_BUDGET_SECONDS,
    LOAD_PROFILE_COMMAND_TIMEOUT_SECONDS,
    LOAD_PROFILE_OPERATION_BUDGET_SECONDS,
    MUTATION_WITH_ROLLBACK_BUDGET_SECONDS,
    SAVE_EDITOR_OPERATION_BUDGET_SECONDS,
    SIDECAR_DEFAULT_TIMEOUT_SECONDS,
    SIDECAR_DEFERRED_TRAIT_TIMEOUT_SECONDS,
)


@dataclass(frozen=True)
class HadesCommandSpec:
    name: str
    timeout_seconds: float
    worst_case_inner_seconds: float
    requires_trusted_target: bool = True
    supports_offline_intent: bool = False


def _spec(
    name: str,
    *,
    timeout: float = DEFAULT_COMMAND_TIMEOUT_SECONDS,
    inner: float = SIDECAR_DEFAULT_TIMEOUT_SECONDS,
    trusted: bool = True,
    offline: bool = False,
) -> HadesCommandSpec:
    return HadesCommandSpec(
        name=name,
        timeout_seconds=float(timeout),
        worst_case_inner_seconds=float(inner),
        requires_trusted_target=bool(trusted),
        supports_offline_intent=bool(offline),
    )


_COMMAND_SPECS = (
    _spec("status"),
    _spec(
        "connect",
        timeout=CONNECT_COMMAND_TIMEOUT_SECONDS,
        inner=CONNECT_OPERATION_BUDGET_SECONDS,
    ),
    _spec("disconnect"),
    _spec(
        "launch",
        timeout=LAUNCH_COMMAND_TIMEOUT_SECONDS,
        inner=LAUNCH_OPERATION_BUDGET_SECONDS,
        trusted=False,
    ),
    _spec("catalog", inner=0.0, trusted=False),
    _spec("diagnostics"),
    _spec("list_profiles", inner=0.0, trusted=False),
    _spec("save_profile", inner=0.0, trusted=False),
    _spec(
        "load_profile",
        timeout=LOAD_PROFILE_COMMAND_TIMEOUT_SECONDS,
        inner=LOAD_PROFILE_OPERATION_BUDGET_SECONDS,
        offline=True,
    ),
    _spec("delete_profile", inner=0.0, trusted=False),
    _spec(
        "set_feature",
        timeout=FEATURE_AND_LOCK_COMMAND_TIMEOUT_SECONDS,
        inner=SIDECAR_DEFAULT_TIMEOUT_SECONDS,
        offline=True,
    ),
    _spec("set_boon_rarity", inner=SIDECAR_DEFAULT_TIMEOUT_SECONDS, offline=True),
    _spec(
        "disable_all",
        timeout=FEATURE_AND_LOCK_COMMAND_TIMEOUT_SECONDS,
        inner=MUTATION_WITH_ROLLBACK_BUDGET_SECONDS,
        offline=True,
    ),
    _spec(
        "lock_vital",
        timeout=FEATURE_AND_LOCK_COMMAND_TIMEOUT_SECONDS,
        inner=MUTATION_WITH_ROLLBACK_BUDGET_SECONDS,
    ),
    _spec(
        "lock_resource",
        timeout=FEATURE_AND_LOCK_COMMAND_TIMEOUT_SECONDS,
        inner=MUTATION_WITH_ROLLBACK_BUDGET_SECONDS,
    ),
    _spec(
        "lock_rerolls",
        timeout=FEATURE_AND_LOCK_COMMAND_TIMEOUT_SECONDS,
        inner=MUTATION_WITH_ROLLBACK_BUDGET_SECONDS,
    ),
    _spec(
        "set_value",
        timeout=FEATURE_AND_LOCK_COMMAND_TIMEOUT_SECONDS,
        inner=MUTATION_WITH_ROLLBACK_BUDGET_SECONDS,
    ),
    _spec("set_resource"),
    _spec("gain_resource"),
    _spec("spawn_reward"),
    _spec("generate_fishing"),
    _spec("generate_chaos_gate"),
    _spec("generate_chamber_object"),
    _spec("apply_world_exit"),
    _spec("cancel_world_exit"),
    _spec("apply_world_occurrence"),
    _spec("cancel_world_occurrence"),
    _spec(
        "add_trait",
        timeout=DEFERRED_TRAIT_COMMAND_TIMEOUT_SECONDS,
        inner=SIDECAR_DEFERRED_TRAIT_TIMEOUT_SECONDS,
    ),
    _spec(
        "update_trait",
        timeout=DEFERRED_TRAIT_COMMAND_TIMEOUT_SECONDS,
        inner=SIDECAR_DEFERRED_TRAIT_TIMEOUT_SECONDS,
    ),
    _spec(
        "remove_trait",
        timeout=DEFERRED_TRAIT_COMMAND_TIMEOUT_SECONDS,
        inner=SIDECAR_DEFERRED_TRAIT_TIMEOUT_SECONDS,
    ),
    _spec(
        "set_trait_uses",
        timeout=DEFERRED_TRAIT_COMMAND_TIMEOUT_SECONDS,
        inner=SIDECAR_DEFERRED_TRAIT_TIMEOUT_SECONDS,
    ),
    _spec(
        "expire_trait",
        timeout=DEFERRED_TRAIT_COMMAND_TIMEOUT_SECONDS,
        inner=SIDECAR_DEFERRED_TRAIT_TIMEOUT_SECONDS,
    ),
    _spec(
        "refresh_trait",
        timeout=DEFERRED_TRAIT_COMMAND_TIMEOUT_SECONDS,
        inner=SIDECAR_DEFERRED_TRAIT_TIMEOUT_SECONDS,
    ),
    _spec(
        "add_chaos_pair",
        timeout=DEFERRED_TRAIT_COMMAND_TIMEOUT_SECONDS,
        inner=SIDECAR_DEFERRED_TRAIT_TIMEOUT_SECONDS,
    ),
    _spec("save_editor_inventory", inner=SAVE_EDITOR_OPERATION_BUDGET_SECONDS, trusted=False),
    _spec("save_editor_open", inner=SAVE_EDITOR_OPERATION_BUDGET_SECONDS, trusted=False),
    _spec("save_editor_target", inner=0.0, trusted=False),
    _spec("save_editor_query", inner=SAVE_EDITOR_OPERATION_BUDGET_SECONDS, trusted=False),
    _spec("save_editor_detail", inner=SAVE_EDITOR_OPERATION_BUDGET_SECONDS, trusted=False),
    _spec("save_editor_stage", inner=0.0, trusted=False),
    _spec("save_editor_unstage", inner=0.0, trusted=False),
    _spec("save_editor_review", inner=0.0, trusted=False),
    _spec("save_editor_cancel", inner=0.0, trusted=False),
    _spec("save_editor_apply", inner=SAVE_EDITOR_OPERATION_BUDGET_SECONDS, trusted=False),
    _spec("save_editor_close", inner=0.0, trusted=False),
)

COMMAND_SPECS = {spec.name: spec for spec in _COMMAND_SPECS}


def command_metadata() -> tuple[dict[str, object], ...]:
    """Stable build metadata for the Swift caller adapter."""
    return tuple(
        {
            "name": spec.name,
            "timeoutSeconds": spec.timeout_seconds,
            "requiresTrustedTarget": spec.requires_trusted_target,
            "supportsOfflineIntent": spec.supports_offline_intent,
        }
        for spec in _COMMAND_SPECS
    )


def command_budget_audit() -> tuple[dict[str, object], ...]:
    """Per-command outer timeout vs worst-case inner budget table."""
    return tuple(
        {
            "name": spec.name,
            "timeoutSeconds": spec.timeout_seconds,
            "worstCaseInnerSeconds": spec.worst_case_inner_seconds,
        }
        for spec in _COMMAND_SPECS
    )
