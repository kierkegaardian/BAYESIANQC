from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import Session

from app.bayesian import (
    _active_prior,
    _risk_from_posterior,
    infer_risk,
    infer_risk_as_of,
    rebuild_posterior_state,
)
from app.db import get_engine
from app.db_models import PriorConfig, QCRecord, StreamConfig
from app.math.distributions import student_t_cdf, student_t_ppf
from app.math.nig import (
    beta_from_expected_sigma,
    update_normal_inverse_gamma,
    validate_nig_parameters,
)
from app.models import (
    BayesianRiskStatus,
    BayesianRiskUnavailableReason,
    DuplicateStatus,
    EntrySource,
)
from app.services.stream_setups import _prior_payload
from app.stream_setup_models import StreamSetupIn
from scripts.demo_kiosk.generator import prior_config
from scripts.demo_kiosk.scenarios import scenario_for_stream


def _config(**overrides: object) -> StreamConfig:
    values: dict[str, object] = {
        "stream_id": "math-stream",
        "analyte": "Control",
        "method": "Method",
        "instrument": "Instrument",
        "qc_level": "L1",
        "control_material_lot": "LOT-1",
        "units": "u",
        "target_value": 0.0,
        "sigma": 1.0,
    }
    values.update(overrides)
    return StreamConfig(**values)  # type: ignore[arg-type]


def test_student_t_matches_reference_quantiles_and_tail_probability() -> None:
    expected_quantiles = {
        4.0: 2.7764451051977987,
        10.0: 2.2281388519649385,
        30.0: 2.042272456301238,
        100.0: 1.9839715184496334,
    }
    for degrees_of_freedom, expected in expected_quantiles.items():
        quantile = student_t_ppf(0.975, degrees_of_freedom)
        assert quantile == pytest.approx(expected, rel=2e-10)
        assert student_t_cdf(quantile, degrees_of_freedom) == pytest.approx(0.975, abs=2e-12)
        assert student_t_cdf(-quantile, degrees_of_freedom) == pytest.approx(0.025, abs=2e-12)

    two_sided_tail = 2.0 * (1.0 - student_t_cdf(3.0, 30.0))
    assert two_sided_tail == pytest.approx(0.0053899640656514, rel=1e-12)


def test_nig_sequential_update_matches_closed_form_and_rejects_nonfinite_inputs() -> None:
    mu0, kappa0, alpha0, beta0 = 10.0, 2.5, 3.0, 4.0
    observations = (9.2, 10.4, 11.1, 9.8, 10.7)
    posterior = (mu0, kappa0, alpha0, beta0)
    for observation in observations:
        posterior = update_normal_inverse_gamma(*posterior, observation)

    count = len(observations)
    sample_mean = sum(observations) / count
    sum_squares = sum((value - sample_mean) ** 2 for value in observations)
    expected = (
        (kappa0 * mu0 + count * sample_mean) / (kappa0 + count),
        kappa0 + count,
        alpha0 + count / 2.0,
        beta0
        + 0.5 * sum_squares
        + (kappa0 * count * (sample_mean - mu0) ** 2) / (2.0 * (kappa0 + count)),
    )
    assert posterior == pytest.approx(expected, rel=1e-12, abs=1e-12)
    assert beta_from_expected_sigma(10.0, 2.0) == pytest.approx(36.0)
    assert beta_from_expected_sigma(10.0, 2.0) / (10.0 - 1.0) == pytest.approx(4.0)

    with pytest.raises(ValueError, match="finite"):
        update_normal_inverse_gamma(0.0, 1.0, 2.0, 1.0, float("nan"))
    with pytest.raises(ValueError, match="finite"):
        validate_nig_parameters(0.0, 1.0, float("inf"), 1.0)
    with pytest.raises(ValueError, match="beta must be finite"):
        beta_from_expected_sigma(2.0, 1e308)


def test_risk_uses_student_t_for_df_30_and_returns_coherent_intervals() -> None:
    risk = _risk_from_posterior(
        mu_n=0.0,
        kappa_n=1.0,
        alpha_n=15.0,
        beta_n=7.5,
        config=_config(),
    )
    assert risk.status == BayesianRiskStatus.AVAILABLE
    assert risk.engine_id == "nig-student-t-v1"
    assert risk.probability_outside_limits == pytest.approx(0.0053899640656514, rel=1e-12)
    assert risk.probability_outside_warning is not None
    assert risk.probability_outside_limits is not None
    assert risk.probability_outside_warning >= risk.probability_outside_limits
    assert risk.credible_interval is not None
    assert risk.predictive_interval is not None
    credible_width = risk.credible_interval[1] - risk.credible_interval[0]
    predictive_width = risk.predictive_interval[1] - risk.predictive_interval[0]
    assert predictive_width > credible_width

    with pytest.raises(ValueError, match="sigma must be finite"):
        _risk_from_posterior(
            mu_n=0.0,
            kappa_n=1.0,
            alpha_n=2.0,
            beta_n=1.0,
            config=_config(sigma=float("nan")),
        )


def test_stream_setup_and_demo_priors_preserve_expected_process_variance() -> None:
    setup = StreamSetupIn(
        stream_id="setup-stream",
        instrument_name="Instrument",
        method_name="Method",
        parameter_name="Control",
        units="u",
        material_name="Material",
        qc_level="L1",
        control_material_lot="LOT-1",
        target_value=100.0,
        sigma=2.0,
        prior_alpha0=10.0,
    )
    payload = _prior_payload(setup)
    assert payload.beta0 == pytest.approx(36.0)

    weak_scenario = scenario_for_stream(3)
    weak_prior = prior_config("demo", 100.0, 2.0, weak_scenario)
    assert weak_prior["beta0"] == pytest.approx(1.0)


def test_future_prior_is_not_applied_before_its_effective_time() -> None:
    now = datetime.now(timezone.utc)
    future_prior = PriorConfig(
        stream_id="future-prior-stream",
        effective_from=now + timedelta(days=1),
        mu0=0.0,
        kappa0=1.0,
        alpha0=2.0,
        beta0=1.0,
    )
    assert _active_prior([future_prior], now) is None

    record = QCRecord(
        stream_id="future-prior-stream",
        timestamp=now,
        result_value=0.2,
        analyte="Control",
        qc_level="L1",
        instrument_id="Instrument",
        method_id="Method",
        control_material_lot="LOT-1",
        units="u",
        entry_source=EntrySource.MANUAL,
        raw_payload={},
        duplicate_status=DuplicateStatus.UNIQUE,
    )
    with Session(get_engine()) as session:
        session.add(future_prior)
        session.add(record)
        session.commit()
        risk = infer_risk(
            session,
            record_value=record.result_value,
            record_timestamp=record.timestamp,
            stream_id=record.stream_id,
            config=_config(stream_id=record.stream_id, effective_from=now - timedelta(days=1)),
        )
        assert risk.status == BayesianRiskStatus.UNAVAILABLE
        assert risk.unavailable_reason == BayesianRiskUnavailableReason.MISSING_EFFECTIVE_PRIOR
        assert rebuild_posterior_state(session, record.stream_id) is None


def test_effective_prior_without_records_uses_prior_predictive_not_zero() -> None:
    now = datetime.now(timezone.utc)
    stream_id = "prior-predictive-empty-stream"
    prior = PriorConfig(
        stream_id=stream_id,
        effective_from=now - timedelta(minutes=1),
        mu0=0.0,
        kappa0=2.0,
        alpha0=3.0,
        beta0=2.0,
    )
    with Session(get_engine()) as session:
        session.add(prior)
        session.commit()
        risk = infer_risk_as_of(session, stream_id, now, _config(stream_id=stream_id))
    assert risk.status == BayesianRiskStatus.AVAILABLE
    assert risk.probability_outside_limits is not None
    assert 0.0 < risk.probability_outside_limits < 1.0
    assert risk.risk_score is not None and risk.risk_score > 0
