from __future__ import annotations

import math
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.math.prior import prior_beta_from_sigma
from app.math.student_t import (
    student_t_cdf,
    student_t_interval_quantile,
    student_t_ppf,
    student_t_probability_outside_bounds,
)
from app.models import PriorConfigIn, QCRecordIn, StreamConfigIn

# Independently recorded R pt/qt reference values.
REFERENCE_VALUES = [
    (4.0, 0.8130495168499705, -7.173182219782321, 2.776445105197799),
    (10.0, 0.8295534338489701, -4.143700494046623, 2.2281388519649385),
    (30.0, 0.8373456922869849, -3.3851848668182165, 2.0422724563012373),
    (100.0, 0.8401379221079384, -3.173739493738782, 1.9839715184496334),
]


def _stream_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "stream_id": "finite-stream",
        "analyte": "Sulfur",
        "method": "ASTM D7039",
        "instrument": "Sindie",
        "qc_level": "L1",
        "control_material_lot": "LOT-1",
        "units": "ppm",
        "target_value": 10.0,
        "sigma": 0.5,
        "warning_limit_sd": 2.0,
        "action_limit_sd": 3.0,
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize(("df", "cdf_at_one", "q001", "q975"), REFERENCE_VALUES)
def test_student_t_matches_reference_values(df: float, cdf_at_one: float, q001: float, q975: float) -> None:
    assert student_t_cdf(1.0, df) == pytest.approx(cdf_at_one, abs=1e-10)
    assert student_t_cdf(-1.0, df) == pytest.approx(1.0 - cdf_at_one, abs=1e-10)
    assert student_t_ppf(0.001, df) == pytest.approx(q001, abs=1e-8)
    assert student_t_ppf(0.975, df) == pytest.approx(q975, abs=1e-8)
    assert student_t_interval_quantile(df) == pytest.approx(q975, abs=1e-8)


@pytest.mark.parametrize("df", [4.0, 10.0, 30.0, 100.0])
@pytest.mark.parametrize("probability", [1e-6, 0.001, 0.025, 0.5, 0.975, 0.999, 1.0 - 1e-6])
def test_student_t_cdf_ppf_round_trip(df: float, probability: float) -> None:
    quantile = student_t_ppf(probability, df)
    assert student_t_cdf(quantile, df) == pytest.approx(probability, abs=1e-10)


@pytest.mark.parametrize("scale", [0.25, 1.0, 10.0])
def test_df_30_three_scale_tail_is_student_t(scale: float) -> None:
    outside = student_t_probability_outside_bounds(
        mean=0.0,
        scale=scale,
        degrees_of_freedom=30.0,
        lower=-3.0 * scale,
        upper=3.0 * scale,
    )
    assert outside == pytest.approx(0.005389964065651934, abs=1e-10)


def test_student_t_has_no_df_30_cutover_discontinuity() -> None:
    below = student_t_probability_outside_bounds(
        mean=0.0, scale=1.0, degrees_of_freedom=29.999999, lower=-3.0, upper=3.0
    )
    at_cutover = student_t_probability_outside_bounds(
        mean=0.0, scale=1.0, degrees_of_freedom=30.0, lower=-3.0, upper=3.0
    )
    above = student_t_probability_outside_bounds(
        mean=0.0, scale=1.0, degrees_of_freedom=30.000001, lower=-3.0, upper=3.0
    )
    assert abs(below - at_cutover) < 1e-9
    assert abs(above - at_cutover) < 1e-9


@pytest.mark.parametrize("df", [4.0, 10.0, 30.0, 100.0])
def test_warning_probability_is_not_below_action_probability(df: float) -> None:
    warning = student_t_probability_outside_bounds(
        mean=0.0, scale=1.0, degrees_of_freedom=df, lower=-2.0, upper=2.0
    )
    action = student_t_probability_outside_bounds(
        mean=0.0, scale=1.0, degrees_of_freedom=df, lower=-3.0, upper=3.0
    )
    assert warning >= action


@pytest.mark.parametrize(
    "overrides",
    [
        {"target_value": math.nan},
        {"sigma": math.inf},
        {"warning_limit_sd": -math.inf},
        {"action_limit_sd": math.nan},
        {"bayes_warn_prob_threshold": math.inf},
        {"bayes_hold_prob_threshold": math.nan},
        {"min_value": 5.0, "max_value": 4.0},
    ],
)
def test_stream_config_rejects_invalid_statistical_values(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        StreamConfigIn.model_validate(_stream_payload(**overrides))


@pytest.mark.parametrize(
    "overrides",
    [
        {"sigma": 0.0},
        {"sigma": -0.5},
        {"warning_limit_sd": 0.0},
        {"action_limit_sd": -3.0},
        {"warning_limit_sd": 3.0, "action_limit_sd": 2.0},
    ],
)
def test_stream_config_rejects_nonpositive_or_reversed_scales(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        StreamConfigIn.model_validate(_stream_payload(**overrides))


@pytest.mark.parametrize(
    "conversion",
    [math.inf, {"factor": math.nan}, {"offset": math.inf}, {"factor": 1.0, "unexpected": 2.0}],
)
def test_stream_config_rejects_invalid_unit_conversions(conversion: object) -> None:
    with pytest.raises(ValidationError):
        StreamConfigIn.model_validate(_stream_payload(unit_conversions={"mg/L": conversion}))


@pytest.mark.parametrize(
    "overrides",
    [
        {"mu0": math.nan},
        {"kappa0": math.inf},
        {"alpha0": -math.inf},
        {"beta0": math.nan},
    ],
)
def test_prior_rejects_nonfinite_parameters(overrides: dict[str, object]) -> None:
    payload: dict[str, object] = {"stream_id": "finite-stream", "mu0": 10.0, "kappa0": 1.0, "alpha0": 2.0}
    payload.update(overrides)
    with pytest.raises(ValidationError):
        PriorConfigIn.model_validate(payload)


@pytest.mark.parametrize(
    "overrides",
    [
        {"kappa0": 0.0},
        {"kappa0": -1.0},
        {"alpha0": 1.0},
        {"alpha0": 0.0},
        {"beta0": 0.0},
        {"beta0": -1.0},
    ],
)
def test_prior_rejects_invalid_scale_parameters(overrides: dict[str, object]) -> None:
    payload: dict[str, object] = {"stream_id": "finite-stream", "mu0": 10.0, "kappa0": 1.0, "alpha0": 2.0}
    payload.update(overrides)
    with pytest.raises(ValidationError):
        PriorConfigIn.model_validate(payload)


def test_prior_beta_may_be_omitted_and_has_variance_preserving_default() -> None:
    prior = PriorConfigIn(stream_id="finite-stream", mu0=10.0, kappa0=1.0, alpha0=5.0)
    assert prior.beta0 is None
    assert prior_beta_from_sigma(prior.alpha0, 0.5) == pytest.approx(1.0)


def test_qc_result_must_be_finite() -> None:
    with pytest.raises(ValidationError):
        QCRecordIn(
            stream_id="finite-stream",
            result_value=math.nan,
            timestamp=datetime(2026, 7, 15, tzinfo=timezone.utc),
            analyte="Sulfur",
            qc_level="L1",
            instrument_id="Sindie",
            method_id="ASTM D7039",
            control_material_lot="LOT-1",
            units="ppm",
        )
