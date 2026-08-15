from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import Column, Enum as SAEnum, Index, JSON, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.evaluation_models import (
    AlertReconciliationOutcome,
    BayesianThresholdMode,
    ControlLimitSource,
    EvaluationTrigger,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _enum_column(enum_type: type) -> Column:
    return Column(
        SAEnum(
            enum_type,
            native_enum=False,
            values_callable=lambda members: [member.value for member in members],
        ),
        nullable=False,
    )


class EvaluationRun(SQLModel, table=True):
    __table_args__ = (Index("ix_evaluationrun_stream_started", "stream_id", "started_at"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: str = Field(index=True, unique=True)
    stream_id: str = Field(index=True)
    trigger: EvaluationTrigger = Field(sa_column=_enum_column(EvaluationTrigger))
    engine_version: str
    frequentist_method: str
    bayesian_method: str
    risk_semantics: str
    actor: str
    reason: str
    input_fingerprint: str = Field(index=True)
    started_at: datetime = Field(default_factory=utcnow)
    completed_at: Optional[datetime] = None
    record_count: int = 0
    changed_record_count: int = 0
    alerts_confirmed: int = 0
    alerts_superseded: int = 0
    alerts_created: int = 0


class QCRecordEvaluation(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint("run_id", "qc_record_id", name="uq_qcrecordevaluation_run_record"),
        Index("ix_qcrecordevaluation_record_time", "qc_record_id", "evaluated_at"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: str = Field(index=True, foreign_key="evaluationrun.run_id")
    qc_record_id: int = Field(index=True, foreign_key="qcrecord.id")
    evaluated_at: datetime = Field(default_factory=utcnow)
    engine_version: str
    frequentist_method: str
    bayesian_method: str
    risk_semantics: str
    stream_config_id: int = Field(index=True, foreign_key="streamconfig.id")
    stream_config_version: int
    prior_config_id: Optional[int] = Field(default=None, index=True, foreign_key="priorconfig.id")
    prior_config_version: Optional[int] = None
    threshold_mode: BayesianThresholdMode = Field(sa_column=_enum_column(BayesianThresholdMode))
    control_limit_source: ControlLimitSource = Field(sa_column=_enum_column(ControlLimitSource))
    applied_centerline: float
    applied_sigma: float
    warning_limit_sd: float
    action_limit_sd: float
    warning_lower: float
    warning_upper: float
    action_lower: float
    action_upper: float
    baseline_start: Optional[datetime] = None
    baseline_end: Optional[datetime] = None
    baseline_count: Optional[int] = None
    signals: list[dict[str, Any]] = Field(sa_column=Column(JSON))
    bayesian_risk: Optional[dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    disposition: str


class AlertEvaluationReconciliation(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "alert_record_id",
            name="uq_alertevaluationreconciliation_run_alert",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: str = Field(index=True, foreign_key="evaluationrun.run_id")
    alert_record_id: int = Field(index=True, foreign_key="alertrecord.id")
    previous_evaluation_id: Optional[int] = Field(
        default=None,
        index=True,
        foreign_key="qcrecordevaluation.id",
    )
    current_evaluation_id: int = Field(index=True, foreign_key="qcrecordevaluation.id")
    outcome: AlertReconciliationOutcome = Field(
        sa_column=_enum_column(AlertReconciliationOutcome)
    )
    replacement_alert_record_id: Optional[int] = Field(
        default=None,
        index=True,
        foreign_key="alertrecord.id",
    )
    actor: str
    reason: str
    created_at: datetime = Field(default_factory=utcnow)
