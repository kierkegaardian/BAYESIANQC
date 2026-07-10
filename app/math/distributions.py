from __future__ import annotations

import math
from functools import lru_cache

from app.math.validation import (
    clamp_probability,
    finite_float,
    open_unit_probability,
    positive_finite_float,
)

DEFAULT_INTERVAL_LEVEL = 0.95
_MAX_CONTINUED_FRACTION_ITERATIONS = 200
_CONTINUED_FRACTION_EPSILON = 3e-12
_CONTINUED_FRACTION_FPMIN = 1e-300
_MAX_PPF_BRACKET = 1e12


def _beta_continued_fraction(a: float, b: float, x: float) -> float:
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0

    c = 1.0
    d = 1.0 - (qab * x / qap)
    if abs(d) < _CONTINUED_FRACTION_FPMIN:
        d = _CONTINUED_FRACTION_FPMIN
    d = 1.0 / d
    result = d

    for m in range(1, _MAX_CONTINUED_FRACTION_ITERATIONS + 1):
        m2 = 2 * m
        coefficient = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + coefficient * d
        if abs(d) < _CONTINUED_FRACTION_FPMIN:
            d = _CONTINUED_FRACTION_FPMIN
        c = 1.0 + coefficient / c
        if abs(c) < _CONTINUED_FRACTION_FPMIN:
            c = _CONTINUED_FRACTION_FPMIN
        d = 1.0 / d
        result *= d * c

        coefficient = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + coefficient * d
        if abs(d) < _CONTINUED_FRACTION_FPMIN:
            d = _CONTINUED_FRACTION_FPMIN
        c = 1.0 + coefficient / c
        if abs(c) < _CONTINUED_FRACTION_FPMIN:
            c = _CONTINUED_FRACTION_FPMIN
        d = 1.0 / d
        delta = d * c
        result *= delta
        if abs(delta - 1.0) < _CONTINUED_FRACTION_EPSILON:
            return result

    raise ArithmeticError("incomplete beta continued fraction did not converge")


def _regularized_incomplete_beta(a: float, b: float, x: float) -> float:
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0

    log_beta_term = (
        math.lgamma(a + b)
        - math.lgamma(a)
        - math.lgamma(b)
        + a * math.log(x)
        + b * math.log1p(-x)
    )
    beta_term = math.exp(log_beta_term)
    if x < (a + 1.0) / (a + b + 2.0):
        return clamp_probability(beta_term * _beta_continued_fraction(a, b, x) / a)
    complement = beta_term * _beta_continued_fraction(b, a, 1.0 - x) / b
    return clamp_probability(1.0 - complement)


def student_t_cdf(t_value: float, degrees_of_freedom: float) -> float:
    value = finite_float("t_value", t_value)
    df = positive_finite_float("degrees_of_freedom", degrees_of_freedom)
    x = df / (df + value * value)
    incomplete_beta = _regularized_incomplete_beta(df / 2.0, 0.5, x)
    if value >= 0.0:
        return clamp_probability(1.0 - 0.5 * incomplete_beta)
    return clamp_probability(0.5 * incomplete_beta)


def student_t_ppf(probability: float, degrees_of_freedom: float) -> float:
    target = open_unit_probability("probability", probability)
    df = positive_finite_float("degrees_of_freedom", degrees_of_freedom)
    if target == 0.5:
        return 0.0
    if target < 0.5:
        return -student_t_ppf(1.0 - target, df)

    upper = 1.0
    while student_t_cdf(upper, df) < target:
        upper *= 2.0
        if upper > _MAX_PPF_BRACKET:
            raise ArithmeticError("could not bracket Student-t quantile")

    lower = 0.0
    for _ in range(100):
        midpoint = (lower + upper) / 2.0
        if student_t_cdf(midpoint, df) < target:
            lower = midpoint
        else:
            upper = midpoint
    return (lower + upper) / 2.0


@lru_cache(maxsize=512)
def student_t_interval_quantile(degrees_of_freedom: float, level: float = DEFAULT_INTERVAL_LEVEL) -> float:
    df = positive_finite_float("degrees_of_freedom", degrees_of_freedom)
    interval_level = open_unit_probability("level", level)
    return student_t_ppf((1.0 + interval_level) / 2.0, df)


def probability_inside_student_t_bounds(
    *,
    mean: float,
    scale: float,
    degrees_of_freedom: float,
    lower: float,
    upper: float,
) -> float:
    location = finite_float("mean", mean)
    predictive_scale = positive_finite_float("scale", scale)
    df = positive_finite_float("degrees_of_freedom", degrees_of_freedom)
    lower_bound = finite_float("lower", lower)
    upper_bound = finite_float("upper", upper)
    if lower_bound > upper_bound:
        raise ValueError("lower must be <= upper")
    upper_probability = student_t_cdf((upper_bound - location) / predictive_scale, df)
    lower_probability = student_t_cdf((lower_bound - location) / predictive_scale, df)
    return clamp_probability(upper_probability - lower_probability)
