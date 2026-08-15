from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import Column, Enum as SAEnum, Index, JSON, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.evaluation_models import ControlLimitSource
from app.models import (
    AlertStatus,
    CapaStatus,
    DuplicateStatus,
    EntrySource,
    EventType,
    InvestigationStatus,
    QCBacklogPriority,
    QCBacklogSource,
    QCBacklogStatus,
    QCCommentTargetType,
    QuarantineReason,
    QuarantineStatus,
    Role,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


DEFAULT_RULE_SET = {"rules": ["1-3s", "2-2s", "4-1s", "10x"]}


class ApiKey(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    key_hash: str = Field(index=True, unique=True)
    key_lookup_hash: Optional[str] = Field(default=None, index=True, unique=True)
    role: Role = Field(sa_column=Column(SAEnum(Role)))
    description: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)
    active: bool = True


class AccessGrant(SQLModel, table=True):
    __table_args__ = (
        Index("ix_accessgrant_api_key_active", "api_key_id", "active"),
        Index("ix_accessgrant_site_bench", "site", "lab_bench"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    api_key_id: int = Field(index=True, foreign_key="apikey.id")
    site: Optional[str] = None
    lab_bench: Optional[str] = None
    stream_id: Optional[str] = Field(default=None, index=True)
    assignment_group: Optional[str] = Field(default=None, index=True)
    active: bool = True
    created_at: datetime = Field(default_factory=utcnow)
    created_by: str = Field(default="system")
    reason: Optional[str] = None


class Instrument(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    site: Optional[str] = None
    lab_bench: Optional[str] = Field(default=None, index=True)
    active: bool = True
    created_at: datetime = Field(default_factory=utcnow)
    created_by: str = Field(default="system")


class Method(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    instrument_id: int = Field(index=True, foreign_key="instrument.id")
    name: str = Field(index=True)
    technique: Optional[str] = None
    active: bool = True
    created_at: datetime = Field(default_factory=utcnow)
    created_by: str = Field(default="system")


class Analyte(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    method_id: int = Field(index=True, foreign_key="method.id")
    name: str = Field(index=True)
    units: Optional[str] = None
    active: bool = True
    created_at: datetime = Field(default_factory=utcnow)
    created_by: str = Field(default="system")


class ControlMaterial(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint(
            "name",
            "lot",
            "qc_level",
            "matrix",
            name="uq_controlmaterial_identity",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    lot: str = Field(index=True)
    qc_level: str = Field(index=True)
    matrix: Optional[str] = None
    manufacturer: Optional[str] = None
    active: bool = True
    created_at: datetime = Field(default_factory=utcnow)
    created_by: str = Field(default="system")


class StreamConfig(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("stream_id", "version", name="uq_streamconfig_stream_version"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    stream_id: str = Field(index=True)
    version: int = Field(default=1, index=True)
    effective_from: datetime = Field(default_factory=utcnow, index=True)
    created_at: datetime = Field(default_factory=utcnow)
    created_by: str = Field(default="system")
    analyte: str
    method: str
    instrument: str
    site: Optional[str] = None
    lab_bench: Optional[str] = Field(default=None, index=True)
    matrix: Optional[str] = None
    qc_level: str
    control_material_lot: str
    control_material_id: Optional[int] = Field(default=None, index=True)
    units: str
    target_value: float
    sigma: float
    action_limit_sd: float = 3.0
    warning_limit_sd: float = 2.0
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    allowed_units: Optional[list[str]] = Field(default=None, sa_column=Column(JSON))
    unit_conversions: Optional[dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    control_limit_source: ControlLimitSource = Field(
        default=ControlLimitSource.CONFIGURED,
        sa_column=Column(
            SAEnum(
                ControlLimitSource,
                native_enum=False,
                values_callable=lambda members: [member.value for member in members],
            ),
            nullable=False,
        ),
    )
    baseline_start: Optional[datetime] = None
    baseline_end: Optional[datetime] = None
    baseline_centerline: Optional[float] = None
    baseline_sigma: Optional[float] = None
    baseline_count: Optional[int] = None
    risk_threshold_warn: int = 50
    risk_threshold_hold: int = 80
    bayes_warn_prob_threshold: Optional[float] = None
    bayes_warn_consecutive: Optional[int] = None
    bayes_hold_prob_threshold: Optional[float] = None
    bayes_hold_consecutive: Optional[int] = None
    rule_set: dict[str, Any] = Field(default_factory=lambda: DEFAULT_RULE_SET.copy(), sa_column=Column(JSON))


class PriorConfig(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("stream_id", "version", name="uq_priorconfig_stream_version"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    stream_id: str = Field(index=True)
    version: int = Field(default=1, index=True)
    effective_from: datetime = Field(default_factory=utcnow, index=True)
    created_at: datetime = Field(default_factory=utcnow)
    created_by: str = Field(default="system")
    mu0: float
    kappa0: float
    alpha0: float
    beta0: float


class PosteriorState(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    stream_id: str = Field(index=True, unique=True)
    updated_at: datetime = Field(default_factory=utcnow)
    prior_id: Optional[int] = Field(default=None, index=True, foreign_key="priorconfig.id")
    config_id: Optional[int] = Field(default=None, index=True, foreign_key="streamconfig.id")
    mu_n: float
    kappa_n: float
    alpha_n: float
    beta_n: float
    n_obs: int = 0
    warn_streak: int = 0
    hold_streak: int = 0


class QCRecord(SQLModel, table=True):
    __table_args__ = (Index("ix_qcrecord_stream_timestamp", "stream_id", "timestamp"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    stream_id: str = Field(index=True)
    timestamp: datetime = Field(index=True)
    result_value: float
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
    flags: Optional[list[str]] = Field(default=None, sa_column=Column(JSON))
    entry_source: EntrySource = Field(sa_column=Column(SAEnum(EntrySource)))
    comments: Optional[str] = None
    include_in_stats: bool = True
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    resolved_reason: Optional[str] = None
    # Snapshotted evaluations for scalable, read-mostly charts.
    signals: Optional[list[dict[str, Any]]] = Field(default=None, sa_column=Column(JSON))
    bayesian_risk: Optional[dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    disposition: Optional[str] = None
    current_evaluation_id: Optional[int] = Field(
        default=None,
        index=True,
    )
    raw_payload: dict[str, Any] = Field(sa_column=Column(JSON))
    duplicate_status: DuplicateStatus = Field(sa_column=Column(SAEnum(DuplicateStatus)))
    created_at: datetime = Field(default_factory=utcnow)
    idempotency_key: Optional[str] = Field(default=None, index=True)
    qc_backlog_item_id: Optional[int] = Field(default=None, index=True)


class QCRecordQuarantine(SQLModel, table=True):
    __table_args__ = (Index("ix_qcrecordquarantine_status_created", "status", "created_at"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    status: QuarantineStatus = Field(default=QuarantineStatus.OPEN, sa_column=Column(SAEnum(QuarantineStatus)))
    reason: QuarantineReason = Field(sa_column=Column(SAEnum(QuarantineReason)))
    reason_detail: str
    stream_id: Optional[str] = Field(default=None, index=True)
    payload: dict[str, Any] = Field(sa_column=Column(JSON))
    context: dict[str, Any] = Field(sa_column=Column(JSON))
    failures: list[dict[str, Any]] = Field(sa_column=Column(JSON))
    actor: str
    actor_role: Optional[Role] = Field(default=None, sa_column=Column(SAEnum(Role), nullable=True))
    api_key_id: Optional[int] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utcnow, index=True)
    reviewed_at: Optional[datetime] = None
    reviewed_by: Optional[str] = None
    review_reason: Optional[str] = None
    qc_record_id: Optional[int] = Field(default=None, index=True)
    idempotency_key: Optional[str] = Field(default=None, index=True)


class QCBacklogItem(SQLModel, table=True):
    __table_args__ = (
        Index("ix_qcbacklogitem_status_due", "status", "due_at"),
        Index("ix_qcbacklogitem_instrument_due", "instrument", "due_at"),
        Index("ix_qcbacklogitem_bench_due", "lab_bench", "due_at"),
        Index("ix_qcbacklogitem_group_due", "assignment_group", "due_at"),
        Index("ix_qcbacklogitem_assignee_due", "assigned_to", "due_at"),
        Index("ix_qcbacklogitem_stream_due", "stream_id", "due_at"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    source: QCBacklogSource = Field(sa_column=Column(SAEnum(QCBacklogSource)))
    status: QCBacklogStatus = Field(default=QCBacklogStatus.OPEN, sa_column=Column(SAEnum(QCBacklogStatus)))
    priority: QCBacklogPriority = Field(
        default=QCBacklogPriority.ROUTINE,
        sa_column=Column(SAEnum(QCBacklogPriority)),
    )
    stream_id: str = Field(index=True)
    analyte: str
    method: str
    instrument: str = Field(index=True)
    site: Optional[str] = None
    qc_level: str
    units: str
    reference_material_lot: str
    reference_material_label: Optional[str] = None
    due_at: datetime = Field(index=True)
    lab_bench: Optional[str] = Field(default=None, index=True)
    assignment_group: Optional[str] = Field(default=None, index=True)
    assigned_to: Optional[str] = Field(default=None, index=True)
    notes: Optional[str] = None
    requested_by: Optional[str] = None
    created_by: str = Field(default="system")
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    started_at: Optional[datetime] = None
    started_by: Optional[str] = None
    completed_at: Optional[datetime] = None
    completed_by: Optional[str] = None
    completed_qc_record_id: Optional[int] = Field(default=None, index=True)
    last_quarantine_id: Optional[int] = Field(default=None, index=True)


class QCComment(SQLModel, table=True):
    __table_args__ = (
        Index("ix_qccomment_target_created", "target_type", "target_id", "created_at"),
        Index("ix_qccomment_stream_created", "stream_id", "created_at"),
        Index("ix_qccomment_qc_record_created", "qc_record_id", "created_at"),
        Index("ix_qccomment_alert_created", "alert_id", "created_at"),
        Index("ix_qccomment_run_created", "run_id", "created_at"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    target_type: QCCommentTargetType = Field(sa_column=Column(SAEnum(QCCommentTargetType)))
    target_id: str = Field(index=True)
    stream_id: Optional[str] = Field(default=None, index=True)
    qc_record_id: Optional[int] = Field(default=None, index=True)
    alert_id: Optional[str] = Field(default=None, index=True)
    run_id: Optional[str] = Field(default=None, index=True)
    body: str
    actor: str
    actor_role: Optional[Role] = Field(default=None, sa_column=Column(SAEnum(Role), nullable=True))
    api_key_id: Optional[int] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utcnow, index=True)


class KioskLayout(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    slug: str = Field(index=True, unique=True)
    label: str
    site: Optional[str] = None
    lab_bench: Optional[str] = None
    active: bool = True
    created_at: datetime = Field(default_factory=utcnow)
    created_by: str = Field(default="system")


class KioskPanel(SQLModel, table=True):
    __table_args__ = (
        Index("ix_kioskpanel_kiosk_order", "kiosk_id", "display_order"),
        Index("ix_kioskpanel_stream", "stream_id"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    kiosk_id: int = Field(index=True, foreign_key="kiosklayout.id")
    stream_id: str = Field(index=True)
    title: str
    display_order: int = Field(index=True)
    start: Optional[str] = None
    end: Optional[str] = None
    window_label: Optional[str] = None
    mode: str = "both"
    active: bool = True
    created_at: datetime = Field(default_factory=utcnow)
    created_by: str = Field(default="system")


class QCEvent(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    stream_id: Optional[str] = Field(default=None, index=True)
    event_type: EventType = Field(sa_column=Column(SAEnum(EventType)))
    timestamp: datetime
    instrument_id: Optional[str] = None
    analyte: Optional[str] = None
    method_id: Optional[str] = None
    event_metadata: Optional[dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    created_by: str = Field(default="system")
    created_at: datetime = Field(default_factory=utcnow)


class AlertRecord(SQLModel, table=True):
    __table_args__ = (Index("ix_alertrecord_stream_created", "stream_id", "created_at"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    alert_id: str = Field(index=True, unique=True)
    stream_id: str = Field(index=True)
    qc_record_id: Optional[int] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utcnow)
    status: AlertStatus = Field(default=AlertStatus.OPEN, sa_column=Column(SAEnum(AlertStatus)))
    severity: str
    disposition: str
    signals: list[dict[str, Any]] = Field(sa_column=Column(JSON))
    bayesian_risk: dict[str, Any] = Field(sa_column=Column(JSON))
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None
    assigned_to: Optional[str] = None
    due_at: Optional[datetime] = None
    source_evaluation_id: Optional[int] = Field(
        default=None,
        index=True,
    )


class Investigation(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    status: InvestigationStatus = Field(
        default=InvestigationStatus.OPEN, sa_column=Column(SAEnum(InvestigationStatus))
    )
    problem_statement: str
    suspected_cause: Optional[str] = None
    containment: Optional[str] = None
    data_reviewed: Optional[str] = None
    outcome: Optional[str] = None
    decision: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    created_by: str = Field(default="system")


class InvestigationAlertLink(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    investigation_id: int = Field(index=True)
    alert_id: int = Field(index=True)


class Capa(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    status: CapaStatus = Field(default=CapaStatus.DRAFT, sa_column=Column(SAEnum(CapaStatus)))
    root_cause_category: Optional[str] = None
    corrective_actions: Optional[list[dict[str, Any]]] = Field(default=None, sa_column=Column(JSON))
    preventive_actions: Optional[list[dict[str, Any]]] = Field(default=None, sa_column=Column(JSON))
    owners: Optional[list[str]] = Field(default=None, sa_column=Column(JSON))
    due_at: Optional[datetime] = None
    verification_plan: Optional[str] = None
    effectiveness_criteria: Optional[dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    created_by: str = Field(default="system")


class CapaLink(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    capa_id: int = Field(index=True)
    alert_id: Optional[int] = Field(default=None, index=True)
    investigation_id: Optional[int] = Field(default=None, index=True)


class AuditEntry(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: datetime = Field(default_factory=utcnow, index=True)
    actor: str
    actor_role: Optional[Role] = Field(default=None, sa_column=Column(SAEnum(Role), nullable=True))
    api_key_id: Optional[int] = Field(default=None, index=True)
    action: str
    entity_type: str
    entity_id: Optional[str] = None
    before: Optional[dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    after: Optional[dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    reason: Optional[str] = None


class IngestionReceipt(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    idempotency_key: str = Field(index=True, unique=True)
    created_at: datetime = Field(default_factory=utcnow)
    response: dict[str, Any] = Field(sa_column=Column(JSON))
    qc_record_id: Optional[int] = Field(default=None, index=True)
    stream_id: Optional[str] = Field(default=None, index=True)
    api_key_id: Optional[int] = Field(default=None, index=True)
