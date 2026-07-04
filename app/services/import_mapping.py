from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlmodel import Session, col, select

from app.db_models import QCBacklogItem, StreamConfig
from app.import_db_models import ImportBatch, ImportRow, ParserProfile
from app.import_models import ImportRowStatus, ImportRowType
from app.models import QCBacklogStatus
from app.services.import_readers import SourceRow
from app.storage import get_active_stream_config

QC_FIELDS = [
    "stream_id",
    "timestamp",
    "result_value",
    "analyte",
    "qc_level",
    "instrument_id",
    "method_id",
    "operator_id",
    "reagent_lot",
    "control_material_lot",
    "calibration_status",
    "run_id",
    "units",
    "comments",
]


def _config_dict(profile: ParserProfile, key: str) -> dict[str, Any]:
    value = profile.config.get(key)
    return value if isinstance(value, dict) else {}


def _mapped_value(raw: dict[str, Any], profile: ParserProfile, field: str) -> Any:
    columns = _config_dict(profile, "columns")
    defaults = _config_dict(profile, "defaults")
    column = columns.get(field)
    if isinstance(column, str) and column in raw and raw[column] not in ("", None):
        return raw[column]
    if field == "timestamp":
        date_column = columns.get("date")
        time_column = columns.get("time")
        if isinstance(date_column, str) and isinstance(time_column, str):
            date_value = raw.get(date_column)
            time_value = raw.get(time_column)
            if date_value and time_value:
                return f"{date_value} {time_value}"
    return defaults.get(field)


def _parse_timestamp(value: Any, profile: ParserProfile) -> tuple[Optional[datetime], Optional[str]]:
    if value in (None, ""):
        return None, "timestamp is required"
    if isinstance(value, datetime):
        return value, None
    text = str(value).strip()
    timestamp_format = profile.config.get("timestamp_format")
    try:
        if isinstance(timestamp_format, str) and timestamp_format:
            parsed = datetime.strptime(text, timestamp_format).replace(tzinfo=timezone.utc)
        else:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None, f"timestamp could not be parsed: {text}"
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed, None


def _parse_result(value: Any, profile: ParserProfile) -> tuple[Optional[float], Optional[str], Optional[str]]:
    if value in (None, ""):
        return None, None, "result_value is required"
    token = str(value).strip()
    token_map = _config_dict(profile, "result_token_map")
    if token in token_map:
        mapped = token_map[token]
        if isinstance(mapped, dict):
            numeric = mapped.get("numeric")
            qualifier = str(mapped.get("qualifier") or token)
        else:
            numeric = mapped
            qualifier = token
        if numeric is None:
            return None, token, f"result token map for {token} is missing numeric"
        try:
            return float(numeric), qualifier, None
        except (TypeError, ValueError):
            return None, token, f"result token map for {token} is not numeric"
    try:
        return float(token), None, None
    except ValueError:
        return None, token, f"result_value is not numeric: {token}"


def _resolve_stream(session: Session, fields: dict[str, Any], timestamp: datetime) -> tuple[Optional[str], list[str]]:
    stream_id = fields.get("stream_id")
    if isinstance(stream_id, str) and stream_id:
        return (stream_id, []) if get_active_stream_config(session, stream_id, timestamp) else (None, ["stream_id is not configured"])
    query = select(StreamConfig).where(StreamConfig.effective_from <= timestamp)
    for attr, field in [
        ("analyte", "analyte"),
        ("method", "method_id"),
        ("instrument", "instrument_id"),
        ("qc_level", "qc_level"),
        ("control_material_lot", "control_material_lot"),
        ("units", "units"),
    ]:
        value = fields.get(field)
        if isinstance(value, str) and value:
            query = query.where(getattr(StreamConfig, attr) == value)
    rows = session.exec(query.order_by(col(StreamConfig.version).desc())).all()
    stream_ids = sorted({row.stream_id for row in rows})
    if len(stream_ids) == 1:
        return stream_ids[0], []
    if len(stream_ids) > 1:
        return None, ["stream mapping is ambiguous"]
    return None, ["stream mapping is required"]


def _fill_from_stream(session: Session, fields: dict[str, Any], stream_id: str, timestamp: datetime) -> None:
    config = get_active_stream_config(session, stream_id, timestamp)
    if not config:
        return
    for field, value in [
        ("stream_id", config.stream_id),
        ("analyte", config.analyte),
        ("qc_level", config.qc_level),
        ("instrument_id", config.instrument),
        ("method_id", config.method),
        ("control_material_lot", config.control_material_lot),
        ("units", config.units),
    ]:
        if fields.get(field) in (None, ""):
            fields[field] = value


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _matching_backlog(session: Session, fields: dict[str, Any], timestamp: datetime, window_hours: float) -> tuple[Optional[int], list[str]]:
    stream_id = fields.get("stream_id")
    if not isinstance(stream_id, str) or not stream_id:
        return None, []
    start = timestamp - timedelta(hours=window_hours)
    end = timestamp + timedelta(hours=window_hours)
    rows = session.exec(
        select(QCBacklogItem).where(
            col(QCBacklogItem.status).in_([QCBacklogStatus.OPEN, QCBacklogStatus.IN_PROGRESS]),
            QCBacklogItem.stream_id == stream_id,
        )
    ).all()
    matches: list[QCBacklogItem] = []
    for row in rows:
        anchor = _as_utc(row.started_at or row.due_at)
        if start <= anchor <= end:
            matches.append(row)
    if len(matches) == 1:
        return matches[0].id, []
    if len(matches) > 1:
        return None, ["backlog/run association is ambiguous"]
    return None, []


def build_import_row(session: Session, batch: ImportBatch, profile: ParserProfile, source: SourceRow) -> ImportRow:
    errors = list(source.errors)
    warnings: list[str] = []
    parsed: dict[str, Any] = {}
    if source.row_type == ImportRowType.QC_RESULT:
        parsed = {field: _mapped_value(source.raw, profile, field) for field in QC_FIELDS}
        parsed["result_raw_token"] = parsed.get("result_value")
        timestamp, timestamp_error = _parse_timestamp(parsed.get("timestamp"), profile)
        if timestamp_error:
            errors.append(timestamp_error)
        else:
            parsed["timestamp"] = timestamp.isoformat() if timestamp else None
        result, qualifier, result_error = _parse_result(parsed.get("result_value"), profile)
        if result_error:
            errors.append(result_error)
        else:
            parsed["result_value"] = result
            if qualifier:
                parsed["result_qualifier"] = qualifier
        if timestamp is not None:
            stream_id, stream_errors = _resolve_stream(session, parsed, timestamp)
            errors.extend(stream_errors)
            if stream_id:
                parsed["stream_id"] = stream_id
                _fill_from_stream(session, parsed, stream_id, timestamp)
                window = float(profile.config.get("matching_window_hours") or 3.0)
                backlog_id, backlog_warnings = _matching_backlog(session, parsed, timestamp, window)
                warnings.extend(backlog_warnings)
                if backlog_id is not None:
                    parsed["qc_backlog_item_id"] = backlog_id
    elif source.row_type == ImportRowType.PEAK:
        parsed = {field: _mapped_value(source.raw, profile, field) for field in ["analyte", "peak_name", "retention_time", "area", "height"]}
    status = ImportRowStatus.IGNORED
    if source.row_type == ImportRowType.QC_RESULT:
        status = ImportRowStatus.READY_TO_APPLY if not errors and not warnings else ImportRowStatus.NEEDS_REVIEW
        if errors:
            status = ImportRowStatus.PARSE_ERROR
    elif source.row_type == ImportRowType.PARSE_ERROR:
        status = ImportRowStatus.PARSE_ERROR
    return ImportRow(
        batch_id=batch.id or 0,
        row_number=source.row_number,
        row_type=source.row_type,
        status=status,
        raw=source.raw,
        parsed_fields={key: value for key, value in parsed.items() if value not in (None, "")},
        warnings=warnings,
        errors=errors,
        stream_id=parsed.get("stream_id") if isinstance(parsed.get("stream_id"), str) else None,
        qc_backlog_item_id=parsed.get("qc_backlog_item_id") if isinstance(parsed.get("qc_backlog_item_id"), int) else None,
        idempotency_key=f"import-row:{batch.file_hash}:{source.row_number}",
    )
