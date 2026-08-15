from __future__ import annotations

import math

from scipy.special import stdtr, stdtrit


def _finite(name: str, value: float) -> float:
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return value


def _degrees_of_freedom(value: float) -> float:
    degrees_of_freedom = _finite("degrees_of_freedom", value)
    if degrees_of_freedom <= 0:
        raise ValueError("degrees_of_freedom must be > 0")
    return degrees_of_freedom


def student_t_cdf(t_value: float, degrees_of_freedom: float) -> float:
    """Return the Student-t cumulative probability for a finite value and df."""

    t = _finite("t_value", t_value)
    df = _degrees_of_freedom(degrees_of_freedom)
    return float(stdtr(df, t))


def student_t_ppf(probability: float, degrees_of_freedom: float) -> float:
    """Return the Student-t quantile for a probability strictly between zero and one."""

    p = _finite("probability", probability)
    if not 0.0 < p < 1.0:
        raise ValueError("probability must be between 0 and 1")
    df = _degrees_of_freedom(degrees_of_freedom)
    return float(stdtrit(df, p))


def student_t_interval_quantile(degrees_of_freedom: float, level: float = 0.95) -> float:
    interval_level = _finite("level", level)
    if not 0.0 < interval_level < 1.0:
        raise ValueError("level must be between 0 and 1")
    probability = (1.0 + interval_level) / 2.0
    return student_t_ppf(probability, degrees_of_freedom)


def student_t_probability_outside_bounds(
    *,
    mean: float,
    scale: float,
    degrees_of_freedom: float,
    lower: float,
    upper: float,
) -> float:
    """Return two-sided probability outside bounds without subtracting from one."""

    center = _finite("mean", mean)
    spread = _finite("scale", scale)
    if spread <= 0:
        raise ValueError("scale must be > 0")
    df = _degrees_of_freedom(degrees_of_freedom)
    lower_bound = _finite("lower", lower)
    upper_bound = _finite("upper", upper)
    if lower_bound > upper_bound:
        raise ValueError("lower must be <= upper")

    lower_t = (lower_bound - center) / spread
    upper_t = (upper_bound - center) / spread
    lower_tail = float(stdtr(df, lower_t))
    upper_tail = float(stdtr(df, -upper_t))
    return max(0.0, min(1.0, lower_tail + upper_tail))
