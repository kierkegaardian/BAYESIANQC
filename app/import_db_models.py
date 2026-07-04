from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import Column, Enum as SAEnum, Index, JSON, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.import_models import (
    CollectorAction,
    CollectorEventType,
    ImportArtifactRole,
    ImportBatchStatus,
    ImportRowStatus,
    ImportRowType,
    ParserProfileStatus,
    ParserProfileType,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ParserProfile(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_parserprofile_name_version"),
        Index("ix_parserprofile_status_type", "status", "profile_type"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    version: int = Field(default=1, index=True)
    profile_type: ParserProfileType = Field(sa_column=Column(SAEnum(ParserProfileType)))
    status: ParserProfileStatus = Field(default=ParserProfileStatus.DRAFT, sa_column=Column(SAEnum(ParserProfileStatus)))
    source_id: Optional[str] = Field(default=None, index=True)
    instrument: Optional[str] = Field(default=None, index=True)
    file_extensions: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    filename_patterns: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    signature: Optional[str] = None
    config: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow)
    created_by: str = Field(default="system")
    updated_at: datetime = Field(default_factory=utcnow)
    updated_by: Optional[str] = None


class ImportBatch(SQLModel, table=True):
    __table_args__ = (
        Index("ix_importbatch_status_received", "status", "received_at"),
        Index("ix_importbatch_hash", "file_hash"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    filename: str = Field(index=True)
    source_id: Optional[str] = Field(default=None, index=True)
    source_path: Optional[str] = None
    file_hash: str = Field(index=True)
    file_size: int
    archived_path: str
    parser_profile_id: Optional[int] = Field(default=None, index=True, foreign_key="parserprofile.id")
    parser_profile_version: Optional[int] = None
    status: ImportBatchStatus = Field(sa_column=Column(SAEnum(ImportBatchStatus)))
    failure_reason: Optional[str] = None
    collector_action: CollectorAction = Field(sa_column=Column(SAEnum(CollectorAction)))
    received_at: datetime = Field(default_factory=utcnow, index=True)
    created_by: str = Field(default="system")
    total_rows: int = 0
    ready_rows: int = 0
    exception_rows: int = 0
    applied_rows: int = 0
    artifact_count: int = 0


class InstrumentRun(SQLModel, table=True):
    __table_args__ = (Index("ix_instrumentrun_key", "run_key"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    run_key: str = Field(index=True, unique=True)
    instrument: Optional[str] = Field(default=None, index=True)
    source_id: Optional[str] = Field(default=None, index=True)
    started_at: Optional[datetime] = Field(default=None, index=True)
    qc_backlog_item_id: Optional[int] = Field(default=None, index=True, foreign_key="qcbacklogitem.id")
    import_batch_id: Optional[int] = Field(default=None, index=True, foreign_key="importbatch.id")
    status: str = Field(default="provisional", index=True)
    created_at: datetime = Field(default_factory=utcnow)


class ImportRow(SQLModel, table=True):
    __table_args__ = (
        Index("ix_importrow_batch_status", "batch_id", "status"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    batch_id: int = Field(index=True, foreign_key="importbatch.id")
    row_number: int
    row_type: ImportRowType = Field(sa_column=Column(SAEnum(ImportRowType)))
    status: ImportRowStatus = Field(sa_column=Column(SAEnum(ImportRowStatus)))
    raw: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    parsed_fields: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    warnings: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    errors: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    stream_id: Optional[str] = Field(default=None, index=True)
    instrument_run_id: Optional[int] = Field(default=None, index=True, foreign_key="instrumentrun.id")
    qc_backlog_item_id: Optional[int] = Field(default=None, index=True, foreign_key="qcbacklogitem.id")
    qc_record_id: Optional[int] = Field(default=None, index=True, foreign_key="qcrecord.id")
    quarantine_id: Optional[int] = Field(default=None, index=True, foreign_key="qcrecordquarantine.id")
    idempotency_key: str = Field(index=True)


class ImportArtifact(SQLModel, table=True):
    __table_args__ = (Index("ix_importartifact_batch_role", "batch_id", "role"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    batch_id: int = Field(index=True, foreign_key="importbatch.id")
    role: ImportArtifactRole = Field(sa_column=Column(SAEnum(ImportArtifactRole)))
    filename: str
    file_hash: str = Field(index=True)
    archived_path: str
    linked_import_row_id: Optional[int] = Field(default=None, index=True, foreign_key="importrow.id")
    instrument_run_id: Optional[int] = Field(default=None, index=True, foreign_key="instrumentrun.id")
    created_at: datetime = Field(default_factory=utcnow)


class InstrumentPeak(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    batch_id: int = Field(index=True, foreign_key="importbatch.id")
    artifact_id: Optional[int] = Field(default=None, index=True, foreign_key="importartifact.id")
    import_row_id: Optional[int] = Field(default=None, index=True, foreign_key="importrow.id")
    analyte: Optional[str] = Field(default=None, index=True)
    peak_name: Optional[str] = None
    retention_time: Optional[float] = None
    area: Optional[float] = None
    height: Optional[float] = None
    raw: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))


class CollectorTransferEvent(SQLModel, table=True):
    __table_args__ = (Index("ix_collectortransfer_transfer_created", "transfer_id", "created_at"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    transfer_id: str = Field(index=True)
    event_type: CollectorEventType = Field(sa_column=Column(SAEnum(CollectorEventType)))
    status: str = Field(index=True)
    source_path: Optional[str] = None
    message: Optional[str] = None
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow, index=True)
    created_by: str = Field(default="system")
