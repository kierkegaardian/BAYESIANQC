from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional, Tuple

from pydantic import BaseModel, Field, field_validator


class Role(str, Enum):
    QC_ANALYST = "qc_analyst"
    SUPERVISOR = "supervisor"
    QA_MANAGER = "qa_manager"
    ADMIN = "admin"
    AUDITOR = "auditor"
    DATA_STEWARD = "data_steward"


class Permission(str, Enum):
    INGEST_QC = "ingest_qc"
    EDIT_CONFIG = "edit_config"
    APPROVE = "approve"
    OVERRIDE = "override"


class EventType(str, Enum):
    CALIBRATION = "calibration"
    MAINTENANCE = "maintenance"
    REAGENT_LOT_CHANGE = "reagent_lot_change"
    CONTROL_MATERIAL_LOT_CHANGE = "control_material_lot_change"
    SOFTWARE_UPDATE = "software_update"
    ENVIRONMENTAL_ALERT = "environmental_alert"


class AlertStatus(str, Enum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    CLOSED = "closed"


class InvestigationStatus(str, Enum):
    OPEN = "open"
    IN_REVIEW = "in_review"
    CLOSED = "closed"


class CapaStatus(str, Enum):
    DRAFT = "draft"
    OPEN = "open"
    IMPLEMENTING = "implementing"
    EFFECTIVENESS_CHECK = "effectiveness_check"
    CLOSED = "closed"
    REOPENED = "reopened"


class EntrySource(str, Enum):
    AUTOMATED = "automated"
    MANUAL = "manual"


class QCRecordIn(BaseModel):
    stream_id: str
    result_value: float
    timestamp: datetime
    analyte: str
    qc_level: str
    instrument_id: str
    method_id: str
    operator_id: Optional[str]
    reagent_lot: Optional[str]
    control_material_lot: str
    calibration_status: Optional[str]
    run_id: Optional[str]
    units: str
    flags: Optional[List[str]] = None
    entry_source: EntrySource = EntrySource.AUTOMATED
    comments: Optional[str]

    @field_validator("result_value")
    @classmethod
    def value_must_be_finite(cls, v: float) -> float:
        if v != v or v in (float("inf"), float("-inf")):
            raise ValueError("Result must be finite")
        return v


class FrequentistSignal(BaseModel):
    rule: str
    severity: str
    evidence: str


class BayesianRisk(BaseModel):
    probability_outside_limits: float
    risk_score: int
    posterior_mean: Optional[float] = None
    posterior_sigma: Optional[float] = None
    predictive_sigma: Optional[float] = None
    credible_interval: Optional[Tuple[float, float]] = None


class QCRecordOut(BaseModel):
    record: QCRecordIn
    signals: List[FrequentistSignal]
    bayesian_risk: BayesianRisk
    disposition: str


class AuditEntryOut(BaseModel):
    timestamp: datetime
    actor: str
    action: str
    entity_type: str
    entity_id: Optional[str] = None
    before: Optional[dict]
    after: dict
    reason: Optional[str]


class AlertOut(BaseModel):
    id: str
    stream_id: str
    created_at: datetime
    signals: List[FrequentistSignal]
    bayesian_risk: BayesianRisk
    disposition: str
    acknowledged: bool = False
    status: Optional[AlertStatus] = None
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None
    assigned_to: Optional[str] = None
    due_at: Optional[datetime] = None


class DuplicateStatus(str, Enum):
    UNIQUE = "unique"
    DUPLICATE = "duplicate"
    POSSIBLE_DUPLICATE = "possible_duplicate"


class IngestionResult(BaseModel):
    status: str
    duplicate: DuplicateStatus
    qc: QCRecordOut
    alert_created: Optional[AlertOut]
    audit_entry: AuditEntryOut
    idempotency_key: Optional[str] = None


class StreamConfigIn(BaseModel):
    stream_id: str
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
    allowed_units: Optional[List[str]] = None
    unit_conversions: Optional[dict] = None
    baseline_start: Optional[datetime] = None
    baseline_end: Optional[datetime] = None
    risk_threshold_warn: int = 50
    risk_threshold_hold: int = 80
    rule_set: Optional[dict] = None
    effective_from: Optional[datetime] = None


class StreamConfigOut(StreamConfigIn):
    version: int
    created_at: datetime
    created_by: str
    effective_from: datetime


class InstrumentIn(BaseModel):
    name: str
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    site: Optional[str] = None
    active: bool = True


class InstrumentOut(InstrumentIn):
    id: int
    created_at: datetime
    created_by: str


class InstrumentUpdate(BaseModel):
    name: Optional[str] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    site: Optional[str] = None
    active: Optional[bool] = None


class MethodIn(BaseModel):
    name: str
    instrument_id: int
    technique: Optional[str] = None
    active: bool = True


class MethodOut(MethodIn):
    id: int
    created_at: datetime
    created_by: str


class MethodUpdate(BaseModel):
    name: Optional[str] = None
    instrument_id: Optional[int] = None
    technique: Optional[str] = None
    active: Optional[bool] = None


class AnalyteIn(BaseModel):
    name: str
    method_id: int
    units: Optional[str] = None
    active: bool = True


class AnalyteOut(AnalyteIn):
    id: int
    created_at: datetime
    created_by: str


class AnalyteUpdate(BaseModel):
    name: Optional[str] = None
    method_id: Optional[int] = None
    units: Optional[str] = None
    active: Optional[bool] = None


class PriorConfigIn(BaseModel):
    stream_id: str
    mu0: float
    kappa0: float
    alpha0: float
    beta0: float
    effective_from: Optional[datetime] = None


class PriorConfigOut(PriorConfigIn):
    version: int
    created_at: datetime
    created_by: str
    effective_from: datetime


class QCEventIn(BaseModel):
    event_type: EventType
    timestamp: datetime
    stream_id: Optional[str] = None
    instrument_id: Optional[str] = None
    analyte: Optional[str] = None
    method_id: Optional[str] = None
    metadata: Optional[dict] = None


class QCEventOut(QCEventIn):
    id: int
    created_at: datetime
    created_by: str


class AlertUpdate(BaseModel):
    status: Optional[AlertStatus] = None
    acknowledged_by: Optional[str] = None
    assigned_to: Optional[str] = None
    due_at: Optional[datetime] = None


class InvestigationIn(BaseModel):
    problem_statement: str
    suspected_cause: Optional[str] = None
    containment: Optional[str] = None
    data_reviewed: Optional[str] = None
    outcome: Optional[str] = None
    decision: Optional[str] = None
    status: Optional[InvestigationStatus] = None
    alert_id: Optional[str] = None


class InvestigationOut(InvestigationIn):
    id: int
    status: InvestigationStatus
    created_at: datetime
    updated_at: datetime
    created_by: str


class CapaIn(BaseModel):
    status: Optional[CapaStatus] = None
    root_cause_category: Optional[str] = None
    corrective_actions: Optional[List[dict]] = None
    preventive_actions: Optional[List[dict]] = None
    owners: Optional[List[str]] = None
    due_at: Optional[datetime] = None
    verification_plan: Optional[str] = None
    effectiveness_criteria: Optional[dict] = None
    alert_id: Optional[str] = None
    investigation_id: Optional[int] = None


class CapaOut(CapaIn):
    id: int
    status: CapaStatus
    created_at: datetime
    updated_at: datetime
    created_by: str
