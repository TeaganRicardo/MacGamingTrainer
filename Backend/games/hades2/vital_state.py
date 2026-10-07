"""Canonical Hades vital lock snapshots and native normalization confirmation."""
import math

from .schema import MAX_AMOUNT, VITALS


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def normalize_vital_locks(raw):
    if not isinstance(raw, dict):
        return {}
    result = {}
    for vital, row in raw.items():
        if vital not in VITALS or not isinstance(row, dict):
            continue
        current = row.get('current')
        minimum = 1 if vital == 'health' else 0
        if not _number(current) or not minimum <= current <= MAX_AMOUNT:
            continue
        normalized = {'current': current}
        if vital != 'armor':
            maximum = row.get('max')
            if not _number(maximum) or not minimum <= maximum <= MAX_AMOUNT:
                continue
            normalized.update(current=min(current, maximum), max=maximum)
        result[vital] = normalized
    return result


def observed_vital_values(vital, observed):
    """Read one complete, attainable vital row from a resident observation."""
    if vital not in VITALS:
        return None
    row = {'current': observed.get(vital)}
    if vital != 'armor':
        row['max'] = observed.get('max' + vital.capitalize())
    normalized = normalize_vital_locks({vital: row}).get(vital)
    return normalized if normalized == row else None


def observed_vital_lock(vital, observed):
    if observed.get(vital + 'Locked') is not True:
        return None
    return observed_vital_values(vital, observed)


def confirmed_replay_vital_lock(vital, wanted, observed):
    """Accept only the game's known current-value clamp after an acknowledged replay.

    Maximum edits must still reach their exact target. Reserved mana is an
    observed native limit, so confirmation never predicts it from desired max.
    """
    actual = observed_vital_lock(vital, observed)
    if actual is None or not isinstance(wanted, dict):
        return None
    current = wanted.get('current')
    if not _number(current):
        return None
    if vital != 'armor':
        maximum = wanted.get('max')
        if not _number(maximum) or abs(actual['max'] - maximum) > 1e-6:
            return None
        current = min(current, maximum)
    if vital == 'mana' and _number(observed.get('availableMana')):
        current = min(current, max(0, observed['availableMana']))
    return actual if abs(actual['current'] - current) <= 1e-6 else None
