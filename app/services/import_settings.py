from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_IMPORT_MAX_UPLOAD_BYTES = 26_214_400
DEFAULT_IMPORT_PARSE_TIMEOUT_SECONDS = 30.0


class ImportSettingsError(RuntimeError):
    pass


@dataclass(frozen=True)
class ImportSettings:
    archive_root: Path
    max_upload_bytes: int
    parse_timeout_seconds: float


def _truthy(value: str | None) -> bool:
    return value is not None and value.strip().lower() in {"1", "true", "yes", "on"}


def default_import_archive_root() -> Path:
    state_home = os.getenv("XDG_STATE_HOME")
    root = Path(state_home).expanduser() if state_home else Path.home() / ".local" / "state"
    return root / "bayesianqc" / "import-archive"


def _positive_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ImportSettingsError(f"{name} must be an integer") from exc
    if parsed <= 0:
        raise ImportSettingsError(f"{name} must be greater than zero")
    return parsed


def _positive_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ImportSettingsError(f"{name} must be numeric") from exc
    if parsed <= 0:
        raise ImportSettingsError(f"{name} must be greater than zero")
    return parsed


def import_settings() -> ImportSettings:
    raw_root = os.getenv("BAYESIANQC_IMPORT_ARCHIVE_ROOT")
    if _truthy(os.getenv("BAYESIANQC_REQUIRE_IMPORT_ARCHIVE_ROOT")) and not raw_root:
        raise ImportSettingsError(
            "BAYESIANQC_IMPORT_ARCHIVE_ROOT must be set when "
            "BAYESIANQC_REQUIRE_IMPORT_ARCHIVE_ROOT=1"
        )
    archive_root = Path(raw_root).expanduser() if raw_root else default_import_archive_root()
    return ImportSettings(
        archive_root=archive_root,
        max_upload_bytes=_positive_int("BAYESIANQC_IMPORT_MAX_UPLOAD_BYTES", DEFAULT_IMPORT_MAX_UPLOAD_BYTES),
        parse_timeout_seconds=_positive_float(
            "BAYESIANQC_IMPORT_PARSE_TIMEOUT_SECONDS",
            DEFAULT_IMPORT_PARSE_TIMEOUT_SECONDS,
        ),
    )
