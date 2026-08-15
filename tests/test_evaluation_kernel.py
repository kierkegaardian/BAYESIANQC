from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.evaluation_models import BayesianThresholdMode, ControlLimitSource
from app.math.control_limits import resolve_control_limits, threshold_mode
from app.math.rules import LEGACY_R4S_VARIANT, evaluate_rule_set
from app.models import StreamConfigIn

NOW = datetime(2026, 7, 15, tzinfo=timezone.utc)


def configured_limits(
    *,
    warning_sd: float = 2,
    action_sd: float = 3,
):
    return resolve_control_limits(
        source=ControlLimitSource.CONFIGURED,
        configured_target=10,
        configured_sigma=2,
        warning_limit_sd=warning_sd,
        action_limit_sd=action_sd,
    )


def stream_payload(**updates: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "stream_id": "stream-1",
        "analyte": "A",
        "method": "M",
        "instrument": "I",
        "qc_level": "L1",
        "control_material_lot": "LOT",
        "units": "u",
        "target_value": 10,
        "sigma": 2,
    }
    payload.update(updates)
    return payload


def test_control_limit_sources_are_finite_and_fixed_baseline_uses_sample_sd() -> None:
    configured = configured_limits()
    assert configured.centerline == 10
    assert configured.sigma == 2
    assert configured.warning_lower == 6
    assert configured.action_upper == 16

    baseline = resolve_control_limits(
        source=ControlLimitSource.FIXED_BASELINE,
        configured_target=99,
        configured_sigma=7,
        warning_limit_sd=2,
        action_limit_sd=3,
        baseline_values=[8, 10, 12],
        baseline_start=NOW,
        baseline_end=NOW,
    )
    assert baseline.centerline == 10
    assert baseline.sigma == 2
    assert baseline.baseline_count == 3


@pytest.mark.parametrize("values", [[], [10], [10, 10]])
def test_fixed_baseline_rejects_insufficient_or_zero_variance(values: list[float]) -> None:
    with pytest.raises((ValueError, ValidationError)):
        resolve_control_limits(
            source=ControlLimitSource.FIXED_BASELINE,
            configured_target=10,
            configured_sigma=1,
            warning_limit_sd=2,
            action_limit_sd=3,
            baseline_values=values,
            baseline_start=NOW,
            baseline_end=NOW,
        )


def test_threshold_modes_support_legacy_reads_without_ordering_explicit_probabilities() -> None:
    assert threshold_mode(0.9, 0.1) == BayesianThresholdMode.EXPLICIT_PROBABILITIES
    assert threshold_mode(None, None) == BayesianThresholdMode.LEGACY_ACTION_RISK_SCORE
    assert threshold_mode(0.5, None) == BayesianThresholdMode.MIXED_LEGACY
    model = StreamConfigIn.model_validate(
        stream_payload(
            bayes_warn_prob_threshold=0.9,
            bayes_hold_prob_threshold=0.1,
        )
    )
    assert model.bayes_warn_prob_threshold == 0.9
    with pytest.raises(ValidationError, match="provided together"):
        StreamConfigIn.model_validate(stream_payload(bayes_warn_prob_threshold=0.5))


def test_new_configs_reject_r4s_but_legacy_rule_is_visibly_variant_tagged() -> None:
    with pytest.raises(ValidationError, match="R-4s"):
        StreamConfigIn.model_validate(stream_payload(rule_set={"rules": ["R-4s"]}))
    signals = evaluate_rule_set(
        record_value=15,
        recent_values=[5],
        limits=configured_limits(),
        rule_ids=["R-4s"],
    )
    assert len(signals) == 1
    assert signals[0].rule_variant == LEGACY_R4S_VARIANT
    assert "Legacy sequential variant" in signals[0].evidence


def test_four_one_s_is_fixed_at_one_sigma_not_warning_limit() -> None:
    signals = evaluate_rule_set(
        record_value=12.2,
        recent_values=[12.1, 12.3, 12.4],
        limits=configured_limits(warning_sd=2.5),
        rule_ids=["4-1s"],
    )
    assert [signal.rule for signal in signals] == ["4-1s"]
