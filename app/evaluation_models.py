from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, FiniteFloat, model_validator


class ControlLimitSource(str, Enum):
    CONFIGURED = "configured"
    FIXED_BASELINE = "fixed_baseline"


class BayesianThresholdMode(str, Enum):
    EXPLICIT_PROBABILITIES = "explicit_probabilities"
    LEGACY_ACTION_RISK_SCORE = "legacy_action_risk_score"
    MIXED_LEGACY = "mixed_legacy"


class EvaluationTrigger(str, Enum):
    INGEST = "ingest"
    OUT_OF_ORDER_INGEST = "out_of_order_ingest"
    RECORD_RESOLUTION = "record_resolution"
    CONFIG_CHANGE = "config_change"
    PRIOR_CHANGE = "prior_change"
    MANUAL_REPROCESS = "manual_reprocess"


class AlertEvaluationStatus(str, Enum):
    CURRENT = "current"
    CONFIRMED = "confirmed"
    SUPERSEDED = "superseded"
    LEGACY_UNVERIFIED = "legacy_unverified"


class AlertReconciliationOutcome(str, Enum):
    CONFIRMED = "confirmed"
    SUPERSEDED = "superseded"


class ResolvedControlLimits(BaseModel):
    source: ControlLimitSource
    centerline: FiniteFloat
    sigma: FiniteFloat
    warning_limit_sd: FiniteFloat
    action_limit_sd: FiniteFloat
    warning_lower: FiniteFloat
    warning_upper: FiniteFloat
    action_lower: FiniteFloat
    action_upper: FiniteFloat
    baseline_start: Optional[datetime] = None
    baseline_end: Optional[datetime] = None
    baseline_count: Optional[int] = Field(default=None, ge=2)

    @model_validator(mode="after")
    def validate_limits(self) -> "ResolvedControlLimits":
        if self.sigma <= 0:
            raise ValueError("resolved sigma must be > 0")
        if self.warning_limit_sd <= 0 or self.action_limit_sd <= 0:
            raise ValueError("resolved limit SD values must be > 0")
        if self.warning_limit_sd > self.action_limit_sd:
            raise ValueError("resolved warning limit must not exceed action limit")
        if not (
            self.action_lower <= self.warning_lower <= self.centerline
            <= self.warning_upper <= self.action_upper
        ):
            raise ValueError("resolved control limits must be ordered")
        if self.source == ControlLimitSource.FIXED_BASELINE:
            if self.baseline_start is None or self.baseline_end is None or self.baseline_count is None:
                raise ValueError("fixed baseline provenance is incomplete")
        return self


class EvaluationProvenanceOut(BaseModel):
    evaluation_id: int
    run_id: str
    evaluated_at: datetime
    engine_version: str
    frequentist_method: str
    bayesian_method: str
    risk_semantics: str
    stream_config_id: int
    stream_config_version: int
    prior_config_id: Optional[int] = None
    prior_config_version: Optional[int] = None
    threshold_mode: BayesianThresholdMode
    limits: ResolvedControlLimits


class EvaluationRecordDiffOut(BaseModel):
    record_id: int
    timestamp: datetime
    old_disposition: Optional[str] = None
    new_disposition: str
    old_rule_ids: list[str] = Field(default_factory=list)
    new_rule_ids: list[str] = Field(default_factory=list)
    old_risk_score: Optional[int] = None
    new_risk_score: int


class EvaluationReprocessPreviewOut(BaseModel):
    stream_id: str
    preview_fingerprint: str
    engine_version: str
    records_scanned: int
    records_changed: int
    alerts_confirmed: int
    alerts_superseded: int
    alerts_to_create: int
    offset: int
    limit: int
    truncated: bool
    changes: list[EvaluationRecordDiffOut]


class EvaluationReprocessApplyIn(BaseModel):
    preview_fingerprint: str = Field(min_length=64, max_length=64)
    reason: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def require_nonblank_reason(self) -> "EvaluationReprocessApplyIn":
        self.reason = self.reason.strip()
        if not self.reason:
            raise ValueError("reason must not be blank")
        return self


class EvaluationReprocessApplyOut(BaseModel):
    run_id: str
    stream_id: str
    engine_version: str
    records_evaluated: int
    records_changed: int
    alerts_confirmed: int
    alerts_superseded: int
    alerts_created: int

