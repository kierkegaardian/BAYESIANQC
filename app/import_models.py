from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, JsonValue, field_validator


class ParserProfileType(str, Enum):
    DELIMITED_DIRECT = "delimited_direct"
    INSTRUMENT_TABLE_DISCOVERY = "instrument_table_discovery"
    XML_MAPPING = "xml_mapping"


class ParserProfileStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"


class ImportBatchStatus(str, Enum):
    RECEIVED = "received"
    FAILED_TO_INGEST = "failed_to_ingest"
    PARSED_WITH_EXCEPTIONS = "parsed_with_exceptions"
    READY_TO_APPLY = "ready_to_apply"
    PARTIALLY_APPLIED = "partially_applied"
    APPLIED = "applied"


class ImportRowType(str, Enum):
    QC_RESULT = "qc_result"
    SAMPLE = "sample"
    EVENT = "event"
    PEAK = "peak"
    IGNORED = "ignored"
    PARSE_ERROR = "parse_error"


class ImportRowStatus(str, Enum):
    READY_TO_APPLY = "ready_to_apply"
    NEEDS_REVIEW = "needs_review"
    PARSE_ERROR = "parse_error"
    IGNORED = "ignored"
    APPLIED = "applied"
    QUARANTINED = "quarantined"


class CollectorAction(str, Enum):
    MOVE_TO_SENT = "move_to_sent"
    MOVE_TO_FAILED = "move_to_failed"
    RETRY_LATER = "retry_later"
    LEAVE_IN_PLACE = "leave_in_place"


class ImportArtifactRole(str, Enum):
    RESULT_REPORT = "result_report"
    CHROMATOGRAM_RAW = "chromatogram_raw"
    CHROMATOGRAM_PDF = "chromatogram_pdf"
    PEAK_TABLE = "peak_table"
    METHOD_FILE = "method_file"
    CALIBRATION_REPORT = "calibration_report"
    UNKNOWN = "unknown"


class CollectorEventType(str, Enum):
    DISCOVERED = "discovered"
    UPLOADED = "uploaded"
    SERVER_ACTION_APPLIED = "server_action_applied"
    FAILED = "failed"


class ParserProfileIn(BaseModel):
    name: str
    profile_type: ParserProfileType
    status: ParserProfileStatus = ParserProfileStatus.DRAFT
    source_id: Optional[str] = None
    instrument: Optional[str] = None
    file_extensions: list[str] = Field(default_factory=list)
    filename_patterns: list[str] = Field(default_factory=list)
    signature: Optional[str] = None
    config: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def name_required(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("name is required")
        return stripped


class ParserProfileUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[ParserProfileStatus] = None
    source_id: Optional[str] = None
    instrument: Optional[str] = None
    file_extensions: Optional[list[str]] = None
    filename_patterns: Optional[list[str]] = None
    signature: Optional[str] = None
    config: Optional[dict[str, JsonValue]] = None
    reason: Optional[str] = None


class ParserProfileOut(ParserProfileIn):
    id: int
    version: int
    created_at: datetime
    created_by: str
    updated_at: datetime
    updated_by: Optional[str] = None


class ImportBatchOut(BaseModel):
    id: int
    filename: str
    source_id: Optional[str] = None
    source_path: Optional[str] = None
    file_hash: str
    file_size: int
    archived_path: str
    parser_profile_id: Optional[int] = None
    parser_profile_version: Optional[int] = None
    status: ImportBatchStatus
    failure_reason: Optional[str] = None
    collector_action: CollectorAction
    received_at: datetime
    created_by: str
    total_rows: int
    ready_rows: int
    exception_rows: int
    applied_rows: int
    artifact_count: int


class ImportRowOut(BaseModel):
    id: int
    batch_id: int
    row_number: int
    row_type: ImportRowType
    status: ImportRowStatus
    raw: dict[str, JsonValue]
    parsed_fields: dict[str, JsonValue]
    warnings: list[str]
    errors: list[str]
    stream_id: Optional[str] = None
    instrument_run_id: Optional[int] = None
    qc_backlog_item_id: Optional[int] = None
    qc_record_id: Optional[int] = None
    quarantine_id: Optional[int] = None
    idempotency_key: str


class ImportArtifactOut(BaseModel):
    id: int
    batch_id: int
    role: ImportArtifactRole
    filename: str
    file_hash: str
    archived_path: str
    linked_import_row_id: Optional[int] = None
    instrument_run_id: Optional[int] = None
    created_at: datetime


class InstrumentPeakOut(BaseModel):
    id: int
    batch_id: int
    artifact_id: Optional[int] = None
    import_row_id: Optional[int] = None
    analyte: Optional[str] = None
    peak_name: Optional[str] = None
    retention_time: Optional[float] = None
    area: Optional[float] = None
    height: Optional[float] = None
    raw: dict[str, JsonValue]


class InstrumentRunOut(BaseModel):
    id: int
    run_key: str
    instrument: Optional[str] = None
    source_id: Optional[str] = None
    started_at: Optional[datetime] = None
    qc_backlog_item_id: Optional[int] = None
    import_batch_id: Optional[int] = None
    status: str
    created_at: datetime


class ImportBatchDetailOut(ImportBatchOut):
    rows: list[ImportRowOut]
    artifacts: list[ImportArtifactOut]
    peaks: list[InstrumentPeakOut]
    instrument_runs: list[InstrumentRunOut]


class ImportCreateOut(BaseModel):
    batch: ImportBatchDetailOut
    collector_action: CollectorAction


class ImportRowUpdate(BaseModel):
    stream_id: Optional[str] = None
    qc_backlog_item_id: Optional[int] = None
    parsed_fields: Optional[dict[str, JsonValue]] = None
    reason: Optional[str] = None


class CollectorTransferEventIn(BaseModel):
    event_type: CollectorEventType
    status: str
    source_path: Optional[str] = None
    message: Optional[str] = None
    payload: dict[str, JsonValue] = Field(default_factory=dict)


class CollectorTransferEventOut(CollectorTransferEventIn):
    id: int
    transfer_id: str
    created_at: datetime
    created_by: str
