from __future__ import annotations

from datetime import datetime
from typing import Literal
from typing import List, Optional

from pydantic import BaseModel, Field, JsonValue, field_validator

from app.configuration_models import PriorConfigBase as PriorConfigBase
from app.configuration_models import PriorConfigIn as PriorConfigIn
from app.configuration_models import PriorConfigOut as PriorConfigOut
from app.configuration_models import StreamCatalogOut as StreamCatalogOut
from app.configuration_models import StreamConfigBase as StreamConfigBase
from app.configuration_models import StreamConfigIn as StreamConfigIn
from app.configuration_models import StreamConfigOut as StreamConfigOut
from app.master_data_models import AnalyteIn as AnalyteIn
from app.master_data_models import AnalyteOut as AnalyteOut
from app.master_data_models import AnalyteUpdate as AnalyteUpdate
from app.master_data_models import EnterpriseSiteIn as EnterpriseSiteIn
from app.master_data_models import EnterpriseSiteOut as EnterpriseSiteOut
from app.master_data_models import EnterpriseSiteUpdate as EnterpriseSiteUpdate
from app.master_data_models import InstrumentIn as InstrumentIn
from app.master_data_models import InstrumentOut as InstrumentOut
from app.master_data_models import InstrumentUpdate as InstrumentUpdate
from app.master_data_models import LabAreaIn as LabAreaIn
from app.master_data_models import LabAreaOut as LabAreaOut
from app.master_data_models import LabAreaUpdate as LabAreaUpdate
from app.master_data_models import MethodIn as MethodIn
from app.master_data_models import MethodOut as MethodOut
from app.master_data_models import MethodUpdate as MethodUpdate
from app.master_data_models import TestCreateIn as TestCreateIn
from app.master_data_models import TestCreateOut as TestCreateOut
from app.model_enums import AlertStatus as AlertStatus
from app.model_enums import BayesianRiskStatus as BayesianRiskStatus
from app.model_enums import BayesianRiskUnavailableReason as BayesianRiskUnavailableReason
from app.model_enums import CapaStatus as CapaStatus
from app.model_enums import DuplicateStatus as DuplicateStatus
from app.model_enums import EntrySource as EntrySource
from app.model_enums import EventType as EventType
from app.model_enums import InvestigationStatus as InvestigationStatus
from app.model_enums import Permission as Permission
from app.model_enums import QCBacklogPriority as QCBacklogPriority
from app.model_enums import QCBacklogSource as QCBacklogSource
from app.model_enums import QCBacklogStatus as QCBacklogStatus
from app.model_enums import QCCommentTargetType as QCCommentTargetType
from app.model_enums import QuarantineReason as QuarantineReason
from app.model_enums import QuarantineStatus as QuarantineStatus
from app.model_enums import Role as Role
from app.statistical_models import BayesianRisk as BayesianRisk
from app.statistical_models import FrequentistSignal as FrequentistSignal
from app.statistical_models import QCRecordIn as QCRecordIn
from app.statistical_models import QCRecordOut as QCRecordOut
from app.statistical_models import QCRecordResolutionIn as QCRecordResolutionIn
from app.statistical_models import QCRecordResolutionOut as QCRecordResolutionOut
from app.workflow_models import AlertOut as AlertOut
from app.workflow_models import AlertUpdate as AlertUpdate
from app.workflow_models import CapaBase as CapaBase
from app.workflow_models import CapaIn as CapaIn
from app.workflow_models import CapaOut as CapaOut
from app.workflow_models import InvestigationBase as InvestigationBase
from app.workflow_models import InvestigationIn as InvestigationIn
from app.workflow_models import InvestigationOut as InvestigationOut


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
