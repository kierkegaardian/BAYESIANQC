from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Tuple

from pydantic import BaseModel, field_validator, model_validator

from app.domain import Disposition, SignalSeverity
from app.model_enums import (
    BayesianRiskStatus,
    BayesianRiskUnavailableReason,
    EntrySource,
)


class QCRecordIn(BaseModel):
    stream_id: str
    result_value: float
    timestamp: datetime
    analyte: str
    qc_level: str
    instrument_id: str
    method_id: str
    operator_id: Optional[str] = None
    reagent_lot: Optional[str] = None
    control_material_lot: str
    calibration_status: Optional[str] = None
    run_id: Optional[str] = None
    units: str
    flags: Optional[List[str]] = None
    entry_source: EntrySource = EntrySource.AUTOMATED
    comments: Optional[str] = None
    qc_backlog_item_id: Optional[int] = None

    @field_validator("result_value")
    @classmethod
    def value_must_be_finite(cls, value: float) -> float:
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError("Result must be finite")
        return value


class FrequentistSignal(BaseModel):
    rule: str
    severity: SignalSeverity
    evidence: str


class BayesianRisk(BaseModel):
    status: BayesianRiskStatus = BayesianRiskStatus.AVAILABLE
    unavailable_reason: Optional[BayesianRiskUnavailableReason] = None
    engine_id: Optional[str] = None
    probability_outside_limits: Optional[float] = None
    probability_outside_warning: Optional[float] = None
    risk_score: Optional[int] = None
    posterior_mean: Optional[float] = None
    posterior_sigma: Optional[float] = None
    predictive_sigma: Optional[float] = None
    credible_interval: Optional[Tuple[float, float]] = None
    predictive_interval: Optional[Tuple[float, float]] = None
    warn_streak: int = 0
    hold_streak: int = 0

    @model_validator(mode="after")
    def evaluation_state_is_consistent(self) -> "BayesianRisk":
        if self.status == BayesianRiskStatus.AVAILABLE:
            if self.probability_outside_limits is None or self.risk_score is None:
                raise ValueError("available Bayesian risk requires probability and risk score")
            if self.unavailable_reason is not None:
                raise ValueError("available Bayesian risk cannot have an unavailable reason")
        elif self.unavailable_reason is None:
            raise ValueError("unavailable Bayesian risk requires a reason")
        return self


class QCRecordOut(BaseModel):
    id: Optional[int] = None
    record: QCRecordIn
    signals: List[FrequentistSignal]
    bayesian_risk: BayesianRisk
    disposition: Disposition


class QCRecordResolutionIn(BaseModel):
    include_in_stats: bool
    resolved_reason: Optional[str] = None


class QCRecordResolutionOut(BaseModel):
    id: int
    stream_id: str
    timestamp: datetime
    result_value: float
    include_in_stats: bool
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    resolved_reason: Optional[str] = None
