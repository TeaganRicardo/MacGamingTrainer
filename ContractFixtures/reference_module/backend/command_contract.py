"""Typed command metadata for the Reference Fixture template module."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReferenceFixtureCommandSpec:
    name: str
    timeout_seconds: float
    worst_case_inner_seconds: float
    requires_trusted_target: bool = True
    supports_offline_intent: bool = False


def _spec(
    name: str,
    *,
    timeout: float = 6.0,
    inner: float = 0.0,
    trusted: bool = True,
    offline: bool = False,
) -> ReferenceFixtureCommandSpec:
    return ReferenceFixtureCommandSpec(
        name=name,
        timeout_seconds=float(timeout),
        worst_case_inner_seconds=float(inner),
        requires_trusted_target=bool(trusted),
        supports_offline_intent=bool(offline),
    )


_COMMAND_SPECS = (
    _spec('status'),
    _spec('connect'),
    _spec('disconnect'),
    _spec('set_enabled', offline=True),
    _spec('disable_all', offline=True),
    _spec('list_profiles', trusted=False),
    _spec('save_profile', trusted=False),
    _spec('load_profile', offline=True),
    _spec('delete_profile', trusted=False),
    _spec('diagnostics', trusted=False),
    _spec('fail', trusted=False),
)

COMMAND_SPECS = {spec.name: spec for spec in _COMMAND_SPECS}


def command_metadata() -> tuple[dict[str, object], ...]:
    """Stable build metadata for the generated Swift command binding."""
    return tuple(
        {
            'name': spec.name,
            'timeoutSeconds': spec.timeout_seconds,
            'requiresTrustedTarget': spec.requires_trusted_target,
            'supportsOfflineIntent': spec.supports_offline_intent,
        }
        for spec in _COMMAND_SPECS
    )


def command_budget_audit() -> tuple[dict[str, object], ...]:
    """Per-command outer timeout vs worst-case inner budget table."""
    return tuple(
        {
            'name': spec.name,
            'timeoutSeconds': spec.timeout_seconds,
            'worstCaseInnerSeconds': spec.worst_case_inner_seconds,
        }
        for spec in _COMMAND_SPECS
    )
