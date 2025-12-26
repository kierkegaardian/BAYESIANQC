from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

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


class QCStream(BaseModel):
    id: str
    analyte: str
    method: str
    instrument: str
    site: Optional[str]
    matrix: Optional[str]
    qc_level: str
    control_material_lot: str
    units: str
    target_value: float
    action_limit_sd: float = Field(3.0, description="Action limit expressed in SD multiples")
    warning_limit_sd: float = Field(2.0, description="Warning limit expressed in SD multiples")
    sigma: float = Field(..., gt=0, description="Baseline sigma for the stream")


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


class QCRecordOut(BaseModel):
    record: QCRecordIn
    signals: List[FrequentistSignal]
    bayesian_risk: BayesianRisk
    disposition: str


class AuditEntry(BaseModel):
    timestamp: datetime
    actor: str
    action: str
    before: Optional[dict]
    after: dict
    reason: Optional[str]


class AuditLog(BaseModel):
    entries: List[AuditEntry] = Field(default_factory=list)

    def append(self, entry: AuditEntry) -> None:
        self.entries.append(entry)


class Alert(BaseModel):
    id: str
    stream_id: str
    created_at: datetime
    signals: List[FrequentistSignal]
    bayesian_risk: BayesianRisk
    disposition: str
    acknowledged: bool = False


class DuplicateStatus(str, Enum):
    UNIQUE = "unique"
    DUPLICATE = "duplicate"
    POSSIBLE_DUPLICATE = "possible_duplicate"


class IngestionResult(BaseModel):
    status: str
    duplicate: DuplicateStatus
    qc: QCRecordOut
    alert_created: Optional[Alert]
    audit_entry: AuditEntry
