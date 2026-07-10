from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.db_models import QCRecord, StreamConfig
from app.frequentist import _recent_values_for_config, evaluate_rules_for_values
from app.models import DuplicateStatus, EntrySource
from scripts.demo_kiosk.generator import stream_config
from scripts.demo_kiosk.scenarios import scenario_for_stream


def _config(*, rules: list[str], **overrides: object) -> StreamConfig:
    values: dict[str, object] = {
        "stream_id": "rules-stream",
        "analyte": "Control",
        "method": "Method",
        "instrument": "Instrument",
        "qc_level": "L1",
        "control_material_lot": "LOT-1",
        "units": "u",
        "target_value": 0.0,
        "sigma": 1.0,
        "warning_limit_sd": 1.5,
        "action_limit_sd": 2.5,
        "rule_set": {"rules": rules},
    }
    values.update(overrides)
    return StreamConfig(**values)  # type: ignore[arg-type]


def _record(timestamp: datetime, result_value: float) -> QCRecord:
    return QCRecord(
        stream_id="rules-stream",
        timestamp=timestamp,
        result_value=result_value,
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


def _rules(record_value: float, recent_values: list[float], config: StreamConfig) -> set[str]:
    return {
        signal.rule
        for signal in evaluate_rules_for_values(
            record_value=record_value,
            target=0.0,
            sigma=1.0,
            recent_values=recent_values,
            config=config,
        )
    }


def test_named_rules_use_fixed_standard_thresholds_and_r4s_is_disabled() -> None:
    config = _config(rules=["1-3s", "2-2s", "R-4s"])
    assert "1-3s" not in _rules(2.6, [], config)
    assert "1-3s" in _rules(3.0, [], config)
    assert "2-2s" not in _rules(1.7, [1.8], config)
    assert "2-2s" in _rules(2.1, [2.2], config)
    assert "R-4s" not in _rules(-2.2, [2.2], config)


def test_run_rules_and_finite_validation() -> None:
    config = _config(rules=["4-1s", "10x"])
    assert "4-1s" in _rules(1.2, [1.1, 1.3, 1.4], config)
    assert "10x" in _rules(0.2, [0.1] * 9, config)
    assert not _rules(0.0, [0.1] * 9, config)

    with pytest.raises(ValueError, match="record_value must be finite"):
        _rules(float("nan"), [], config)
    with pytest.raises(ValueError, match="sigma must be finite"):
        evaluate_rules_for_values(
            record_value=0.0,
            target=0.0,
            sigma=float("inf"),
            recent_values=[],
            config=config,
        )


def test_history_resets_at_config_boundary_and_demo_does_not_claim_r4s() -> None:
    boundary = datetime.now(timezone.utc)
    config = _config(rules=["2-2s"], effective_from=boundary)
    records = [
        _record(boundary - timedelta(minutes=1), 2.2),
        _record(boundary, 2.1),
        _record(boundary + timedelta(minutes=1), 2.3),
    ]
    assert _recent_values_for_config(records, config) == [2.1, 2.3]

    demo_scenario = scenario_for_stream(10)
    assert demo_scenario.scenario_id == "alternating_variability"
    assert "R-4s" not in demo_scenario.label
    demo_stream = stream_config("demo", "A", "M", "I", {"site": "S"}, "L1", "u", 1.0, 0.1, "LOT")
    assert "R-4s" not in demo_stream["rule_set"]["rules"]
