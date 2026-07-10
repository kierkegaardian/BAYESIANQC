from __future__ import annotations

import math
from collections.abc import Iterable


def finite_float(name: str, value: float) -> float:
    """Return ``value`` as a finite float or raise a domain-specific error."""
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result

def positive_finite_float(name: str, value: float) -> float:
    result = finite_float(name, value)
    if result <= 0.0:
        raise ValueError(f"{name} must be > 0")
    return result


def finite_float_tuple(name: str, values: Iterable[float]) -> tuple[float, ...]:
    return tuple(finite_float(f"{name}[{index}]", value) for index, value in enumerate(values))


def clamp_probability(value: float) -> float:
    result = finite_float("probability", value)
    return max(0.0, min(1.0, result))


def open_unit_probability(name: str, value: float) -> float:
    result = finite_float(name, value)
    if not 0.0 < result < 1.0:
        raise ValueError(f"{name} must be between 0 and 1 (exclusive)")
    return result
