from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from app.models import AuditEntry, QCRecordIn, QCStream, DuplicateStatus


class InMemoryStorage:
    def __init__(self) -> None:
        self.streams: Dict[str, QCStream] = {}
        self.qc_records: List[QCRecordIn] = []
        self.audit_log: List[AuditEntry] = []
        self.recent_results_by_stream: Dict[str, List[QCRecordIn]] = defaultdict(list)

    def add_stream(self, stream: QCStream) -> None:
        self.streams[stream.id] = stream

    def get_stream(self, stream_id: str) -> Optional[QCStream]:
        return self.streams.get(stream_id)

    def detect_duplicate(self, record: QCRecordIn) -> DuplicateStatus:
        for existing in self.qc_records:
            if (
                existing.stream_id == record.stream_id
                and existing.timestamp == record.timestamp
                and existing.result_value == record.result_value
            ):
                return DuplicateStatus.DUPLICATE
        for existing in self.qc_records:
            if existing.stream_id == record.stream_id and existing.timestamp == record.timestamp:
                return DuplicateStatus.POSSIBLE_DUPLICATE
        return DuplicateStatus.UNIQUE

    def add_record(self, record: QCRecordIn) -> DuplicateStatus:
        duplicate_status = self.detect_duplicate(record)
        self.qc_records.append(record)
        self.recent_results_by_stream[record.stream_id].append(record)
        self.recent_results_by_stream[record.stream_id] = self.recent_results_by_stream[record.stream_id][-5:]
        return duplicate_status

    def add_audit_entry(self, entry: AuditEntry) -> None:
        self.audit_log.append(entry)

    def get_recent_for_stream(self, stream_id: str, count: int = 5) -> List[QCRecordIn]:
        return self.recent_results_by_stream.get(stream_id, [])[-count:]

    def baseline_stats(self, stream_id: str) -> Optional[Tuple[float, float]]:
        stream = self.get_stream(stream_id)
        if not stream:
            return None
        return stream.target_value, stream.sigma


storage = InMemoryStorage()


# Seed a minimal QC stream so the API can be exercised immediately.
storage.add_stream(
    QCStream(
        id="hba1c-arch",
        analyte="HbA1c",
        method="HPLC",
        instrument="Architect",
        site="Main Lab",
        matrix=None,
        qc_level="Level 1",
        control_material_lot="LOT-001",
        units="%",
        target_value=5.2,
        sigma=0.25,
    )
)
