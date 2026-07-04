from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from sqlmodel import Session, col, select

from app.db import get_engine
from app.db_models import ApiKey, AuditEntry, QCRecord
from app.import_db_models import ImportBatch, InstrumentPeak
from app.import_models import ImportBatchStatus
from app.main import app
from app.models import Role
from app.security import api_key_lookup_hash, hash_api_key
from app.services.import_settings import import_settings
AUTH_HEADERS = {"X-API-Key": "local-dev-key"}
ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "samples" / "import_readiness"


@pytest.fixture(autouse=True)
def import_readiness_archive_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BAYESIANQC_IMPORT_ARCHIVE_ROOT", str(tmp_path / "import-archive"))


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def _add_key(raw_key: str, role: Role) -> dict[str, str]:
    with Session(get_engine()) as session:
        session.add(
            ApiKey(
                key_hash=hash_api_key(raw_key),
                key_lookup_hash=api_key_lookup_hash(raw_key),
                role=role,
                description=f"import readiness {role.value}",
            )
        )
        session.commit()
    return {"X-API-Key": raw_key}


async def _create_profile(client: httpx.AsyncClient, payload: dict[str, object]) -> int:
    response = await client.post("/qc/import-profiles", json=payload, headers=AUTH_HEADERS)
    assert response.status_code == 200, response.text
    return int(response.json()["id"])


async def _create_stream(
    client: httpx.AsyncClient,
    *,
    stream_id: str,
    analyte: str,
    method: str,
    instrument: str,
    qc_level: str,
    lot: str,
    units: str,
    target: float,
    sigma: float,
) -> None:
    response = await client.post(
        "/streams",
        json={
            "stream_id": stream_id,
            "analyte": analyte,
            "method": method,
            "instrument": instrument,
            "site": "Fuel Lab",
            "lab_bench": "Petroleum Bench 1",
            "qc_level": qc_level,
            "control_material_lot": lot,
            "units": units,
            "target_value": target,
            "sigma": sigma,
            "action_limit_sd": 3.0,
            "warning_limit_sd": 2.0,
            "risk_threshold_warn": 50,
            "risk_threshold_hold": 80,
        },
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200, response.text


def _sequence_profile() -> dict[str, object]:
    return {
        "name": "Synthetic OpenLab sequence CSV",
        "profile_type": "delimited_direct",
        "status": "active",
        "file_extensions": [".csv"],
        "filename_patterns": ["*.csv"],
        "config": {
            "delimiter": ",",
            "row_type_column": "Injection Type",
            "row_type_values": {
                "qc_result": ["CheckStandard"],
                "ignored": ["Matrix", "Blank"],
                "event": ["SystemSuitability"],
            },
            "columns": {
                "timestamp": "Acquired At",
                "result_value": "Result",
                "analyte": "Analyte",
                "qc_level": "Level",
                "instrument_id": "Instrument",
                "method_id": "Method",
                "control_material_lot": "Lot",
                "units": "Units",
                "run_id": "Run ID",
            },
            "defaults": {"stream_id": "hba1c-arch"},
        },
    }


def _xml_profile() -> dict[str, object]:
    return {
        "name": "Synthetic middleware XML",
        "profile_type": "xml_mapping",
        "status": "active",
        "file_extensions": [".xml"],
        "filename_patterns": ["*.xml"],
        "config": {
            "rows_path": ".//Result",
            "columns": {
                "timestamp": "timestamp",
                "result_value": "result_value",
                "analyte": "analyte",
                "qc_level": "qc_level",
                "instrument_id": "instrument_id",
                "method_id": "method_id",
                "control_material_lot": "control_material_lot",
                "units": "units",
                "run_id": "run_id",
            },
            "defaults": {"stream_id": "hba1c-arch"},
        },
    }


@pytest.mark.anyio
async def test_source_backed_csv_applies_only_configured_qc_rows(client: httpx.AsyncClient) -> None:
    await _create_profile(client, _sequence_profile())
    data = (FIXTURES / "openlab_sequence_results.csv").read_bytes()

    upload = await client.post("/qc/imports", files={"file": ("openlab_sequence_results.csv", data, "text/csv")}, headers=AUTH_HEADERS)
    assert upload.status_code == 200, upload.text
    body = upload.json()["batch"]
    assert [row["row_type"] for row in body["rows"]] == ["qc_result", "ignored", "event", "qc_result"]
    assert [row["status"] for row in body["rows"]] == ["ready_to_apply", "ignored", "ignored", "ready_to_apply"]

    applied = await client.post(f"/qc/imports/{body['id']}/apply", headers=AUTH_HEADERS)
    assert applied.status_code == 200, applied.text
    assert applied.json()["status"] == "applied"

    duplicate = await client.post(
        "/qc/imports",
        files={"file": ("openlab_sequence_results.csv", data, "text/csv")},
        data={"auto_apply": "true"},
        headers=AUTH_HEADERS,
    )
    assert duplicate.status_code == 200, duplicate.text
    with Session(get_engine()) as session:
        assert len(session.exec(select(QCRecord).where(QCRecord.stream_id == "hba1c-arch")).all()) == 2
        actions = {row.action for row in session.exec(select(AuditEntry)).all()}
    assert {"create_parser_profile", "create_import_batch", "ingest_qc"} <= actions


@pytest.mark.anyio
async def test_d86_table_discovery_xml_and_peak_paths(client: httpx.AsyncClient) -> None:
    await _create_stream(
        client,
        stream_id="d86-t50-diesel",
        analyte="D86 T50",
        method="ASTM D86",
        instrument="OptiDist-100",
        qc_level="Verification",
        lot="D86-CAL-01",
        units="degF",
        target=480.0,
        sigma=8.0,
    )
    d86_profile = _sequence_profile()
    d86_profile.update({"name": "Synthetic D86 DAT", "profile_type": "instrument_table_discovery", "file_extensions": [".dat"], "filename_patterns": ["*.dat"]})
    d86_profile["config"] = {
        "delimiter": ",",
        "table_start": "RESULT TABLE",
        "analyte_column": "Test",
        "expected_tests": [{"name": "D86 T50", "aliases": ["D86 T50"]}],
        "columns": {
            "timestamp": "Timestamp",
            "result_value": "Value",
            "analyte": "Test",
            "qc_level": "Level",
            "instrument_id": "Instrument",
            "method_id": "Method",
            "control_material_lot": "Lot",
            "units": "Units",
        },
        "defaults": {"stream_id": "d86-t50-diesel"},
    }
    await _create_profile(client, d86_profile)
    d86_upload = await client.post(
        "/qc/imports",
        files={"file": ("d86_distillation_report.dat", (FIXTURES / "d86_distillation_report.dat").read_bytes(), "text/plain")},
        headers=AUTH_HEADERS,
    )
    assert d86_upload.status_code == 200, d86_upload.text
    assert [row["row_type"] for row in d86_upload.json()["batch"]["rows"]] == ["ignored", "qc_result", "ignored"]

    await _create_profile(client, _xml_profile())
    xml_upload = await client.post(
        "/qc/imports",
        files={"file": ("middleware_results.xml", (FIXTURES / "middleware_results.xml").read_bytes(), "application/xml")},
        headers=AUTH_HEADERS,
    )
    assert xml_upload.status_code == 200, xml_upload.text
    assert xml_upload.json()["batch"]["ready_rows"] == 1

    peak_profile = _sequence_profile()
    peak_profile.update({"name": "Synthetic Chromeleon peaks", "file_extensions": [".txt"], "filename_patterns": ["*.txt"]})
    peak_profile["config"] = {
        "delimiter": "\\t",
        "peak_table": True,
        "artifact_role": "peak_table",
        "columns": {"analyte": "Analyte", "peak_name": "Peak", "retention_time": "RT", "area": "Area", "height": "Height"},
    }
    await _create_profile(client, peak_profile)
    peak_upload = await client.post(
        "/qc/imports",
        files={"file": ("chromeleon_peak_table.txt", (FIXTURES / "chromeleon_peak_table.txt").read_bytes(), "text/plain")},
        headers=AUTH_HEADERS,
    )
    assert peak_upload.status_code == 200, peak_upload.text
    assert peak_upload.json()["batch"]["artifact_count"] == 1
    with Session(get_engine()) as session:
        assert len(session.exec(select(InstrumentPeak)).all()) == 2


@pytest.mark.anyio
async def test_rbac_failed_file_path_traversal_and_xxe_checks(client: httpx.AsyncClient, tmp_path: Path) -> None:
    supervisor = _add_key("readiness-supervisor-key", Role.SUPERVISOR)
    auditor = _add_key("readiness-auditor-key", Role.AUDITOR)
    profile_create = await client.post("/qc/import-profiles", json=_sequence_profile(), headers=supervisor)
    assert profile_create.status_code == 200, profile_create.text
    assert (await client.post("/qc/imports", files={"file": ("denied.csv", b"x", "text/csv")}, headers=auditor)).status_code == 403
    assert (await client.get("/qc/imports", headers=auditor)).status_code == 200
    assert (await client.get("/qc/imports", headers={"X-API-Key": "invalid"})).status_code == 401

    data = (FIXTURES / "openlab_sequence_results.csv").read_bytes()
    traversal = await client.post("/qc/imports", files={"file": ("../../escape.csv", data, "text/csv")}, headers=AUTH_HEADERS)
    assert traversal.status_code == 200, traversal.text
    archive_root = tmp_path / "import-archive"
    Path(traversal.json()["batch"]["archived_path"]).resolve().relative_to(archive_root.resolve())

    await _create_profile(client, _xml_profile())
    xxe = await client.post(
        "/qc/imports",
        files={"file": ("malicious_entity.xml", (FIXTURES / "malicious_entity.xml").read_bytes(), "application/xml")},
        headers=AUTH_HEADERS,
    )
    assert xxe.status_code == 200, xxe.text
    assert xxe.json()["batch"]["status"] == "failed_to_ingest"

    unknown = await client.post("/qc/imports", files={"file": ("unknown.raw", b"not configured", "application/octet-stream")}, headers=AUTH_HEADERS)
    assert unknown.status_code == 200, unknown.text
    assert unknown.json()["batch"]["collector_action"] == "move_to_failed"
    with Session(get_engine()) as session:
        assert len(session.exec(select(ImportBatch).order_by(col(ImportBatch.id))).all()) >= 3


@pytest.mark.anyio
async def test_oversized_import_is_rejected_by_configured_limit(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BAYESIANQC_IMPORT_MAX_UPLOAD_BYTES", "1024")
    allowed = await client.post("/qc/imports", files={"file": ("large.csv", b"x" * 1024, "text/csv")}, headers=AUTH_HEADERS)
    assert allowed.status_code != 413
    response = await client.post("/qc/imports", files={"file": ("large.csv", b"x" * 1025, "text/csv")}, headers=AUTH_HEADERS)
    assert response.status_code == 413


@pytest.mark.anyio
async def test_import_without_run_or_backlog_requires_manual_association(client: httpx.AsyncClient) -> None:
    profile = _sequence_profile()
    config = profile["config"]
    assert isinstance(config, dict)
    columns = dict(config["columns"])
    columns.pop("run_id")
    config["columns"] = columns
    await _create_profile(client, profile)
    upload = await client.post(
        "/qc/imports",
        files={"file": ("openlab_sequence_results.csv", (FIXTURES / "openlab_sequence_results.csv").read_bytes(), "text/csv")},
        headers=AUTH_HEADERS,
    )
    assert upload.status_code == 200, upload.text
    first_row = upload.json()["batch"]["rows"][0]
    assert first_row["status"] == "needs_review"
    assert first_row["warnings"] == ["run/backlog association is required"]
    patch = await client.patch(f"/qc/imports/rows/{first_row['id']}", json={"stream_id": "hba1c-arch"}, headers=AUTH_HEADERS)
    assert patch.status_code == 422
    assert "run/backlog association is required" in patch.text


@pytest.mark.anyio
async def test_allow_provisional_profile_can_apply_without_run_or_backlog(client: httpx.AsyncClient) -> None:
    profile = _sequence_profile()
    config = profile["config"]
    assert isinstance(config, dict)
    config["run_context_policy"] = "allow_provisional"
    columns = dict(config["columns"])
    columns.pop("run_id")
    config["columns"] = columns
    await _create_profile(client, profile)
    upload = await client.post(
        "/qc/imports",
        files={"file": ("openlab_sequence_results.csv", (FIXTURES / "openlab_sequence_results.csv").read_bytes(), "text/csv")},
        headers=AUTH_HEADERS,
    )
    assert upload.status_code == 200, upload.text
    batch = upload.json()["batch"]
    assert batch["rows"][0]["status"] == "ready_to_apply"
    applied = await client.post(f"/qc/imports/{batch['id']}/apply", headers=AUTH_HEADERS)
    assert applied.status_code == 200, applied.text
    assert applied.json()["status"] == "applied"
    assert applied.json()["instrument_runs"][0]["run_key"] == f"import-{batch['id']}"


@pytest.mark.anyio
async def test_parse_timeout_returns_controlled_failure(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _create_profile(client, _sequence_profile())
    monkeypatch.setenv("BAYESIANQC_IMPORT_PARSE_TIMEOUT_SECONDS", "0.001")
    response = await client.post(
        "/qc/imports",
        files={"file": ("openlab_sequence_results.csv", (FIXTURES / "openlab_sequence_results.csv").read_bytes(), "text/csv")},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 408
    with Session(get_engine()) as session:
        batch = session.exec(select(ImportBatch)).one()
        assert batch.status == ImportBatchStatus.FAILED_TO_INGEST
        assert batch.failure_reason is not None
        assert "timeout" in batch.failure_reason.lower()
    monkeypatch.setenv("BAYESIANQC_IMPORT_PARSE_TIMEOUT_SECONDS", "30")
    recovered = await client.post(
        "/qc/imports",
        files={"file": ("openlab_sequence_results.csv", (FIXTURES / "openlab_sequence_results.csv").read_bytes(), "text/csv")},
        headers=AUTH_HEADERS,
    )
    assert recovered.status_code == 200, recovered.text
    assert recovered.json()["batch"]["ready_rows"] == 2


def test_import_archive_default_is_outside_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BAYESIANQC_IMPORT_ARCHIVE_ROOT", raising=False)
    monkeypatch.delenv("BAYESIANQC_REQUIRE_IMPORT_ARCHIVE_ROOT", raising=False)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    settings = import_settings()
    settings.archive_root.resolve().relative_to((tmp_path / "state").resolve())
    with pytest.raises(ValueError):
        settings.archive_root.resolve().relative_to(ROOT.resolve())


@pytest.mark.anyio
async def test_required_archive_root_fails_without_explicit_setting(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("BAYESIANQC_IMPORT_ARCHIVE_ROOT", raising=False)
    monkeypatch.setenv("BAYESIANQC_REQUIRE_IMPORT_ARCHIVE_ROOT", "1")
    response = await client.post(
        "/qc/imports",
        files={"file": ("openlab_sequence_results.csv", (FIXTURES / "openlab_sequence_results.csv").read_bytes(), "text/csv")},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 500
    assert "BAYESIANQC_IMPORT_ARCHIVE_ROOT must be set" in response.text
