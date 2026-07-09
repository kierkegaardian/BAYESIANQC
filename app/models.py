from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal
from typing import List, Optional, Tuple

from pydantic import BaseModel, Field, JsonValue, field_validator, model_validator

from app.domain import Disposition, SignalSeverity


class Role(str, Enum):
    QC_ANALYST = "qc_analyst"
    SUPERVISOR = "supervisor"
    QA_MANAGER = "qa_manager"
    ADMIN = "admin"
    AUDITOR = "auditor"
    DATA_STEWARD = "data_steward"


class Permission(str, Enum):
    READ = "read"
    INGEST_QC = "ingest_qc"
    EDIT_CONFIG = "edit_config"
    MANAGE_IMPORTS = "manage_imports"
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


class QuarantineReason(str, Enum):
    OUT_OF_BOUNDS = "out_of_bounds"
    UNIT_MISMATCH = "unit_mismatch"
    SUSPICIOUS_TIMESTAMP = "suspicious_timestamp"
    MAPPING_FAILURE = "mapping_failure"


class QuarantineStatus(str, Enum):
    OPEN = "open"
    REVIEWED = "reviewed"
    REJECTED = "rejected"


class QCBacklogSource(str, Enum):
    SCHEDULED = "scheduled"
    REQUESTED = "requested"


class QCBacklogStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELED = "canceled"


class QCBacklogPriority(str, Enum):
    ROUTINE = "routine"
    SOON = "soon"
    URGENT = "urgent"


class QCCommentTargetType(str, Enum):
    QC_RECORD = "qc_record"
    ALERT = "alert"
    QC_RUN = "qc_run"


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
    def value_must_be_finite(cls, v: float) -> float:
        if v != v or v in (float("inf"), float("-inf")):
            raise ValueError("Result must be finite")
        return v


class FrequentistSignal(BaseModel):
    rule: str
    severity: SignalSeverity
    evidence: str


class BayesianRisk(BaseModel):
    probability_outside_limits: float
    probability_outside_warning: float = 0.0
    risk_score: int
    posterior_mean: Optional[float] = None
    posterior_sigma: Optional[float] = None
    predictive_sigma: Optional[float] = None
    credible_interval: Optional[Tuple[float, float]] = None
    predictive_interval: Optional[Tuple[float, float]] = None
    warn_streak: int = 0
    hold_streak: int = 0


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


class AuditEntryOut(BaseModel):
    timestamp: datetime
    actor: str
    actor_role: Optional[Role] = None
    api_key_id: Optional[int] = None
    action: str
    entity_type: str
    entity_id: Optional[str] = None
    before: Optional[dict[str, JsonValue]]
    after: dict[str, JsonValue]
    reason: Optional[str]


class QuarantineFailureOut(BaseModel):
    reason: QuarantineReason
    detail: str
    field: Optional[str] = None


class QCRecordQuarantineOut(BaseModel):
    id: int
    status: QuarantineStatus
    reason: QuarantineReason
    reason_detail: str
    stream_id: Optional[str] = None
    payload: dict[str, JsonValue]
    context: dict[str, JsonValue]
    failures: List[QuarantineFailureOut]
    actor: str
    actor_role: Optional[Role] = None
    api_key_id: Optional[int] = None
    created_at: datetime
    reviewed_at: Optional[datetime] = None
    reviewed_by: Optional[str] = None
    review_reason: Optional[str] = None
    qc_record_id: Optional[int] = None
    idempotency_key: Optional[str] = None


class QuarantineReviewIn(BaseModel):
    status: QuarantineStatus
    review_reason: str

    @field_validator("review_reason")
    @classmethod
    def review_reason_required(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("review_reason is required")
        return stripped

    @field_validator("status")
    @classmethod
    def status_must_be_review_decision(cls, value: QuarantineStatus) -> QuarantineStatus:
        if value == QuarantineStatus.OPEN:
            raise ValueError("status must be reviewed or rejected")
        return value


class EffectiveScopeOut(BaseModel):
    unrestricted: bool
    enforced: bool
    sites: List[str] = Field(default_factory=list)
    lab_benches: List[str] = Field(default_factory=list)
    stream_ids: List[str] = Field(default_factory=list)
    assignment_groups: List[str] = Field(default_factory=list)


class CurrentUserOut(BaseModel):
    role: Role
    api_key_id: Optional[int]
    permissions: List[Permission]
    effective_scope: EffectiveScopeOut


class EnterpriseSiteIn(BaseModel):
    name: str
    code: Optional[str] = None
    description: Optional[str] = None
    active: bool = True

    @field_validator("name")
    @classmethod
    def site_name_required(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("name is required")
        return stripped

    @field_validator("code", "description")
    @classmethod
    def optional_text_stripped(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class EnterpriseSiteOut(EnterpriseSiteIn):
    id: int
    created_at: datetime
    created_by: str


class EnterpriseSiteUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    description: Optional[str] = None
    active: Optional[bool] = None

    @field_validator("name")
    @classmethod
    def update_site_name_required(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("name is required")
        return stripped


class LabAreaIn(BaseModel):
    site_id: int
    name: str
    description: Optional[str] = None
    active: bool = True

    @field_validator("name")
    @classmethod
    def area_name_required(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("name is required")
        return stripped

    @field_validator("description")
    @classmethod
    def area_description_stripped(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class LabAreaOut(LabAreaIn):
    id: int
    site_name: str
    created_at: datetime
    created_by: str


class LabAreaUpdate(BaseModel):
    site_id: Optional[int] = None
    name: Optional[str] = None
    description: Optional[str] = None
    active: Optional[bool] = None

    @field_validator("name")
    @classmethod
    def update_area_name_required(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("name is required")
        return stripped


class AlertOut(BaseModel):
    id: str
    stream_id: str
    created_at: datetime
    qc_record_id: Optional[int] = None
    qc_record_timestamp: Optional[datetime] = None
    signals: List[FrequentistSignal]
    bayesian_risk: BayesianRisk
    disposition: Disposition
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


class QuarantineResult(BaseModel):
    status: Literal["quarantined"] = "quarantined"
    quarantine: QCRecordQuarantineOut
    audit_entry: AuditEntryOut
    idempotency_key: Optional[str] = None


class QCBacklogItemIn(BaseModel):
    source: QCBacklogSource
    stream_id: str
    due_at: datetime
    priority: QCBacklogPriority = QCBacklogPriority.ROUTINE
    lab_bench: Optional[str] = None
    assignment_group: Optional[str] = None
    assigned_to: Optional[str] = None
    reference_material_label: Optional[str] = None
    notes: Optional[str] = None
    requested_by: Optional[str] = None


class QCBacklogItemUpdate(BaseModel):
    status: Optional[QCBacklogStatus] = None
    priority: Optional[QCBacklogPriority] = None
    due_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    lab_bench: Optional[str] = None
    assignment_group: Optional[str] = None
    assigned_to: Optional[str] = None
    reference_material_label: Optional[str] = None
    notes: Optional[str] = None
    reason: Optional[str] = None


class QCBacklogItemOut(BaseModel):
    id: int
    source: QCBacklogSource
    status: QCBacklogStatus
    priority: QCBacklogPriority
    stream_id: str
    analyte: str
    method: str
    instrument: str
    site: Optional[str] = None
    qc_level: str
    units: str
    reference_material_lot: str
    reference_material_label: Optional[str] = None
    due_at: datetime
    lab_bench: Optional[str] = None
    assignment_group: Optional[str] = None
    assigned_to: Optional[str] = None
    notes: Optional[str] = None
    requested_by: Optional[str] = None
    created_by: str
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime] = None
    started_by: Optional[str] = None
    completed_at: Optional[datetime] = None
    completed_by: Optional[str] = None
    completed_qc_record_id: Optional[int] = None
    last_quarantine_id: Optional[int] = None


class QCCommentIn(BaseModel):
    target_type: QCCommentTargetType
    target_id: str
    body: str
    stream_id: Optional[str] = None

    @field_validator("target_id", "body")
    @classmethod
    def text_required(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value is required")
        return stripped


class QCCommentOut(BaseModel):
    id: int
    target_type: QCCommentTargetType
    target_id: str
    stream_id: Optional[str] = None
    qc_record_id: Optional[int] = None
    alert_id: Optional[str] = None
    run_id: Optional[str] = None
    body: str
    actor: str
    actor_role: Optional[Role] = None
    api_key_id: Optional[int] = None
    created_at: datetime


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

    @field_validator("sigma")
    @classmethod
    def sigma_must_be_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("sigma must be > 0")
        return v

    @field_validator("warning_limit_sd", "action_limit_sd")
    @classmethod
    def limits_must_be_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("limit SD values must be > 0")
        return v

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
        if self.bayes_warn_prob_threshold is not None and not (0 <= self.bayes_warn_prob_threshold <= 1):
            raise ValueError("bayes_warn_prob_threshold must be between 0 and 1")
        if self.bayes_hold_prob_threshold is not None and not (0 <= self.bayes_hold_prob_threshold <= 1):
            raise ValueError("bayes_hold_prob_threshold must be between 0 and 1")
        if self.bayes_warn_consecutive is not None and self.bayes_warn_consecutive <= 0:
            raise ValueError("bayes_warn_consecutive must be > 0")
        if self.bayes_hold_consecutive is not None and self.bayes_hold_consecutive <= 0:
            raise ValueError("bayes_hold_consecutive must be > 0")
        if self.baseline_start and self.baseline_end and self.baseline_end < self.baseline_start:
            raise ValueError("baseline_end must be >= baseline_start")
        return self


class StreamConfigIn(StreamConfigBase):
    effective_from: Optional[datetime] = None


class StreamConfigOut(StreamConfigBase):
    version: int
    created_at: datetime
    created_by: str
    effective_from: datetime


class InstrumentIn(BaseModel):
    name: str
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    site_id: Optional[int] = None
    lab_area_id: Optional[int] = None
    site: Optional[str] = None
    lab_bench: Optional[str] = None
    active: bool = True

    @field_validator("name")
    @classmethod
    def instrument_name_required(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("name is required")
        return stripped


class InstrumentOut(InstrumentIn):
    id: int
    created_at: datetime
    created_by: str


class InstrumentUpdate(BaseModel):
    name: Optional[str] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    site_id: Optional[int] = None
    lab_area_id: Optional[int] = None
    site: Optional[str] = None
    lab_bench: Optional[str] = None
    active: Optional[bool] = None


class MethodIn(BaseModel):
    name: str
    instrument_id: int
    technique: Optional[str] = None
    description: Optional[str] = None
    active: bool = True

    @field_validator("name")
    @classmethod
    def method_name_required(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("name is required")
        return stripped


class MethodOut(MethodIn):
    id: int
    created_at: datetime
    created_by: str


class MethodUpdate(BaseModel):
    name: Optional[str] = None
    instrument_id: Optional[int] = None
    technique: Optional[str] = None
    description: Optional[str] = None
    active: Optional[bool] = None


class AnalyteIn(BaseModel):
    name: str
    method_id: int
    units: Optional[str] = None
    result_resolution: Optional[float] = None
    description: Optional[str] = None
    active: bool = True

    @field_validator("name")
    @classmethod
    def analyte_name_required(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("name is required")
        return stripped

    @field_validator("result_resolution")
    @classmethod
    def result_resolution_positive(cls, value: Optional[float]) -> Optional[float]:
        if value is not None and value <= 0:
            raise ValueError("result_resolution must be > 0")
        return value


class AnalyteOut(AnalyteIn):
    id: int
    created_at: datetime
    created_by: str


class AnalyteUpdate(BaseModel):
    name: Optional[str] = None
    method_id: Optional[int] = None
    units: Optional[str] = None
    result_resolution: Optional[float] = None
    description: Optional[str] = None
    active: Optional[bool] = None

    @field_validator("result_resolution")
    @classmethod
    def update_result_resolution_positive(cls, value: Optional[float]) -> Optional[float]:
        if value is not None and value <= 0:
            raise ValueError("result_resolution must be > 0")
        return value


class TestCreateIn(BaseModel):
    instrument_id: int
    name: str
    technique: Optional[str] = None
    description: Optional[str] = None
    analyte_name: str
    analyte_units: str
    analyte_result_resolution: float
    analyte_description: Optional[str] = None
    active: bool = True

    @field_validator("name", "analyte_name", "analyte_units")
    @classmethod
    def test_text_required(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value is required")
        return stripped

    @field_validator("analyte_result_resolution")
    @classmethod
    def test_resolution_positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("analyte_result_resolution must be > 0")
        return value


class TestCreateOut(BaseModel):
    method: MethodOut
    analyte: AnalyteOut


class PriorConfigBase(BaseModel):
    stream_id: str
    mu0: float
    kappa0: float
    alpha0: float
    beta0: float

    @field_validator("kappa0")
    @classmethod
    def kappa0_must_be_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("kappa0 must be > 0")
        return v

    @field_validator("alpha0")
    @classmethod
    def alpha0_must_be_gt_one(cls, v: float) -> float:
        if v <= 1:
            raise ValueError("alpha0 must be > 1")
        return v

    @field_validator("beta0")
    @classmethod
    def beta0_must_be_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("beta0 must be > 0")
        return v


class PriorConfigIn(PriorConfigBase):
    effective_from: Optional[datetime] = None


class PriorConfigOut(PriorConfigBase):
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
    metadata: Optional[dict[str, JsonValue]] = None


class QCEventOut(QCEventIn):
    id: int
    created_at: datetime
    created_by: str


class AlertUpdate(BaseModel):
    status: Optional[AlertStatus] = None
    acknowledged_by: Optional[str] = None
    assigned_to: Optional[str] = None
    due_at: Optional[datetime] = None
    reason: Optional[str] = None


class InvestigationBase(BaseModel):
    problem_statement: str
    suspected_cause: Optional[str] = None
    containment: Optional[str] = None
    data_reviewed: Optional[str] = None
    outcome: Optional[str] = None
    decision: Optional[str] = None
    alert_id: Optional[str] = None


class InvestigationIn(InvestigationBase):
    status: Optional[InvestigationStatus] = None
    reason: Optional[str] = None


class InvestigationOut(InvestigationBase):
    id: int
    status: InvestigationStatus
    created_at: datetime
    updated_at: datetime
    created_by: str


class CapaBase(BaseModel):
    root_cause_category: Optional[str] = None
    corrective_actions: Optional[List[dict[str, JsonValue]]] = None
    preventive_actions: Optional[List[dict[str, JsonValue]]] = None
    owners: Optional[List[str]] = None
    due_at: Optional[datetime] = None
    verification_plan: Optional[str] = None
    effectiveness_criteria: Optional[dict[str, JsonValue]] = None
    alert_id: Optional[str] = None
    investigation_id: Optional[int] = None


class CapaIn(CapaBase):
    status: Optional[CapaStatus] = None
    reason: Optional[str] = None


class CapaOut(CapaBase):
    id: int
    status: CapaStatus
    created_at: datetime
    updated_at: datetime
    created_by: str
