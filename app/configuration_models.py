from __future__ import annotations

from datetime import datetime
from math import isfinite
from typing import List, Optional

from pydantic import BaseModel, JsonValue, field_validator, model_validator


class StreamConfigBase(BaseModel):
    stream_id: str
    analyte: str
    method: str
    instrument: str
    site: Optional[str] = None
    lab_bench: Optional[str] = None
    matrix: Optional[str] = None
    qc_level: str
    control_material_lot: str
    control_material_id: Optional[int] = None
    units: str
    target_value: float
    sigma: float
    action_limit_sd: float = 3.0
    warning_limit_sd: float = 2.0
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    allowed_units: Optional[List[str]] = None
    unit_conversions: Optional[dict[str, JsonValue]] = None
    baseline_start: Optional[datetime] = None
    baseline_end: Optional[datetime] = None
    risk_threshold_warn: int = 50
    risk_threshold_hold: int = 80
    bayes_warn_prob_threshold: Optional[float] = None
    bayes_warn_consecutive: Optional[int] = None
    bayes_hold_prob_threshold: Optional[float] = None
    bayes_hold_consecutive: Optional[int] = None
    rule_set: Optional[dict[str, JsonValue]] = None

    @field_validator(
        "target_value",
        "sigma",
        "warning_limit_sd",
        "action_limit_sd",
        "min_value",
        "max_value",
        "bayes_warn_prob_threshold",
        "bayes_hold_prob_threshold",
    )
    @classmethod
    def statistical_values_must_be_finite(cls, value: Optional[float]) -> Optional[float]:
        if value is not None and not isfinite(value):
            raise ValueError("statistical values must be finite")
        return value

    @field_validator("sigma")
    @classmethod
    def sigma_must_be_positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("sigma must be > 0")
        return value

    @field_validator("warning_limit_sd", "action_limit_sd")
    @classmethod
    def limits_must_be_positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("limit SD values must be > 0")
        return value

    @field_validator("unit_conversions")
    @classmethod
    def conversions_must_be_finite(
        cls,
        value: Optional[dict[str, JsonValue]],
    ) -> Optional[dict[str, JsonValue]]:
        if value is None:
            return None
        for source_unit, conversion in value.items():
            if not source_unit.strip():
                raise ValueError("unit conversion source unit is required")
            if isinstance(conversion, bool):
                raise ValueError("unit conversion must be numeric or an object")
            if isinstance(conversion, (int, float)):
                if not isfinite(float(conversion)) or float(conversion) == 0:
                    raise ValueError("unit conversion factor must be finite and non-zero")
                continue
            if not isinstance(conversion, dict):
                raise ValueError("unit conversion must be numeric or an object")
            factor = conversion.get("factor")
            offset = conversion.get("offset", 0.0)
            if isinstance(factor, bool) or not isinstance(factor, (int, float)):
                raise ValueError("unit conversion factor must be numeric")
            if isinstance(offset, bool) or not isinstance(offset, (int, float)):
                raise ValueError("unit conversion offset must be numeric")
            invalid_factor = not isfinite(float(factor)) or float(factor) == 0
            if invalid_factor or not isfinite(float(offset)):
                raise ValueError(
                    "unit conversion factor and offset must be finite; factor must be non-zero"
                )
        return value

    @field_validator("rule_set")
    @classmethod
    def r4s_requires_within_run_grouping(
        cls,
        value: Optional[dict[str, JsonValue]],
    ) -> Optional[dict[str, JsonValue]]:
        if value is None:
            return None
        rules = value.get("rules", [])
        if not isinstance(rules, list):
            raise ValueError("rule_set.rules must be a list")
        if any(str(rule).strip().lower() == "r-4s" for rule in rules):
            raise ValueError(
                "R-4s requires within-run across-control grouping and is not yet supported"
            )
        return value

    @model_validator(mode="after")
    def validate_limits_and_thresholds(self) -> "StreamConfigBase":
        if self.action_limit_sd < self.warning_limit_sd:
            raise ValueError("action_limit_sd must be >= warning_limit_sd")
        if not (0 <= self.risk_threshold_warn <= 100):
            raise ValueError("risk_threshold_warn must be between 0 and 100")
        if not (0 <= self.risk_threshold_hold <= 100):
            raise ValueError("risk_threshold_hold must be between 0 and 100")
        if self.risk_threshold_hold < self.risk_threshold_warn:
            raise ValueError("risk_threshold_hold must be >= risk_threshold_warn")
        if self.bayes_warn_prob_threshold is not None and not (
            0 <= self.bayes_warn_prob_threshold <= 1
        ):
            raise ValueError("bayes_warn_prob_threshold must be between 0 and 1")
        if self.bayes_hold_prob_threshold is not None and not (
            0 <= self.bayes_hold_prob_threshold <= 1
        ):
            raise ValueError("bayes_hold_prob_threshold must be between 0 and 1")
        if self.bayes_warn_consecutive is not None and self.bayes_warn_consecutive <= 0:
            raise ValueError("bayes_warn_consecutive must be > 0")
        if self.bayes_hold_consecutive is not None and self.bayes_hold_consecutive <= 0:
            raise ValueError("bayes_hold_consecutive must be > 0")
        if (self.baseline_start is None) != (self.baseline_end is None):
            raise ValueError("baseline_start and baseline_end must be provided together")
        if self.baseline_start and self.baseline_end and self.baseline_end < self.baseline_start:
            raise ValueError("baseline_end must be >= baseline_start")
        if self.min_value is not None and self.max_value is not None and self.min_value > self.max_value:
            raise ValueError("min_value must be <= max_value")
        return self


class StreamConfigIn(StreamConfigBase):
    effective_from: Optional[datetime] = None


class StreamConfigOut(StreamConfigBase):
    version: int
    created_at: datetime
    created_by: str
    effective_from: datetime


class StreamCatalogOut(BaseModel):
    """Active, display-only stream fields safe for stakeholder workflows."""

    stream_id: str
    analyte: str
    method: str
    instrument: str
    qc_level: str
    control_material_lot: str
    units: str
    target_value: float
    sigma: float
    action_limit_sd: float
    warning_limit_sd: float
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    risk_threshold_warn: int
    risk_threshold_hold: int
    bayes_warn_prob_threshold: Optional[float] = None
    bayes_warn_consecutive: Optional[int] = None
    bayes_hold_prob_threshold: Optional[float] = None
    bayes_hold_consecutive: Optional[int] = None


class PriorConfigBase(BaseModel):
    stream_id: str
    mu0: float
    kappa0: float
    alpha0: float
    beta0: float

    @field_validator("mu0", "kappa0", "alpha0", "beta0")
    @classmethod
    def prior_values_must_be_finite(cls, value: float) -> float:
        if not isfinite(value):
            raise ValueError("prior values must be finite")
        return value

    @field_validator("kappa0")
    @classmethod
    def kappa0_must_be_positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("kappa0 must be > 0")
        return value

    @field_validator("alpha0")
    @classmethod
    def alpha0_must_be_gt_one(cls, value: float) -> float:
        if value <= 1:
            raise ValueError("alpha0 must be > 1")
        return value

    @field_validator("beta0")
    @classmethod
    def beta0_must_be_positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("beta0 must be > 0")
        return value


class PriorConfigIn(PriorConfigBase):
    beta0: Optional[float] = None
    effective_from: Optional[datetime] = None


class PriorConfigOut(PriorConfigBase):
    version: int
    created_at: datetime
    created_by: str
    effective_from: datetime
