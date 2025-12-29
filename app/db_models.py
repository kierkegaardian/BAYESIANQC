from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, Enum as SAEnum, JSON
from sqlmodel import Field, SQLModel

from app.models import (
    AlertStatus,
    CapaStatus,
    DuplicateStatus,
    EntrySource,
    EventType,
    InvestigationStatus,
    Role,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


DEFAULT_RULE_SET = {"rules": ["1-3s", "2-2s", "R-4s", "4-1s", "10x"]}


class ApiKey(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    key_hash: str = Field(index=True, unique=True)
    role: Role = Field(sa_column=Column(SAEnum(Role)))
    description: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)
    active: bool = True


class StreamConfig(SQLModel, table=True):
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
    matrix: Optional[str] = None
    qc_level: str
    control_material_lot: str
    units: str
    target_value: float
    sigma: float
    action_limit_sd: float = 3.0
    warning_limit_sd: float = 2.0
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    allowed_units: Optional[list[str]] = Field(default=None, sa_column=Column(JSON))
    unit_conversions: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    baseline_start: Optional[datetime] = None
    baseline_end: Optional[datetime] = None
    risk_threshold_warn: int = 50
    risk_threshold_hold: int = 80
    rule_set: dict = Field(default_factory=lambda: DEFAULT_RULE_SET.copy(), sa_column=Column(JSON))


class PriorConfig(SQLModel, table=True):
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
    stream_id: str = Field(index=True)
    updated_at: datetime = Field(default_factory=utcnow)
    mu_n: float
    kappa_n: float
    alpha_n: float
    beta_n: float
    n_obs: int = 0


class QCRecord(SQLModel, table=True):
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
    raw_payload: dict = Field(sa_column=Column(JSON))
    duplicate_status: DuplicateStatus = Field(sa_column=Column(SAEnum(DuplicateStatus)))
    created_at: datetime = Field(default_factory=utcnow)
    idempotency_key: Optional[str] = Field(default=None, index=True)


class QCEvent(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    stream_id: Optional[str] = Field(default=None, index=True)
    event_type: EventType = Field(sa_column=Column(SAEnum(EventType)))
    timestamp: datetime
    instrument_id: Optional[str] = None
    analyte: Optional[str] = None
    method_id: Optional[str] = None
    event_metadata: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    created_by: str = Field(default="system")
    created_at: datetime = Field(default_factory=utcnow)


class AlertRecord(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    alert_id: str = Field(index=True, unique=True)
    stream_id: str = Field(index=True)
    qc_record_id: Optional[int] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utcnow)
    status: AlertStatus = Field(default=AlertStatus.OPEN, sa_column=Column(SAEnum(AlertStatus)))
    severity: str
    disposition: str
    signals: list[dict] = Field(sa_column=Column(JSON))
    bayesian_risk: dict = Field(sa_column=Column(JSON))
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None
    assigned_to: Optional[str] = None
    due_at: Optional[datetime] = None


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
    corrective_actions: Optional[list[dict]] = Field(default=None, sa_column=Column(JSON))
    preventive_actions: Optional[list[dict]] = Field(default=None, sa_column=Column(JSON))
    owners: Optional[list[str]] = Field(default=None, sa_column=Column(JSON))
    due_at: Optional[datetime] = None
    verification_plan: Optional[str] = None
    effectiveness_criteria: Optional[dict] = Field(default=None, sa_column=Column(JSON))
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
    action: str
    entity_type: str
    entity_id: Optional[str] = None
    before: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    after: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    reason: Optional[str] = None


class IngestionReceipt(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    idempotency_key: str = Field(index=True, unique=True)
    created_at: datetime = Field(default_factory=utcnow)
    response: dict = Field(sa_column=Column(JSON))
    qc_record_id: Optional[int] = Field(default=None, index=True)
