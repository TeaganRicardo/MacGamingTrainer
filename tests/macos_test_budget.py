"""Bound outer macOS fixture-process variance for slower hosted runner profiles."""
import os

ENVIRONMENT_VARIABLE = "MGT_MACOS_OUTER_TIMEOUT_SCALE"
MAXIMUM_SCALE = 2.0


def scaled_outer_timeout(seconds: float) -> float:
    if seconds <= 0:
        raise ValueError("outer process timeout must be positive")
    raw = os.environ.get(ENVIRONMENT_VARIABLE, "1.0")
    try:
        scale = float(raw)
    except ValueError as error:
        raise ValueError(f"{ENVIRONMENT_VARIABLE} must be numeric") from error
    if not 1.0 <= scale <= MAXIMUM_SCALE:
        raise ValueError(
            f"{ENVIRONMENT_VARIABLE} must be between 1.0 and {MAXIMUM_SCALE:.1f}"
        )
    return seconds * scale
