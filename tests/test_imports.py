from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from io import BytesIO

import httpx
import pytest
from openpyxl import Workbook
from sqlmodel import Session, select

from app.db import get_engine
from app.db_models import ApiKey, QCRecord
from app.import_db_models import CollectorTransferEvent, ImportBatch, InstrumentPeak
from app.main import app
from app.models import Role
from app.security import api_key_lookup_hash, hash_api_key

AUTH_HEADERS = {"X-API-Key": "local-dev-key"}


@pytest.fixture(autouse=True)
def import_archive_root(tmp_path, monkeypatch) -> None:
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
                description=f"test {role.value}",
            )
        )
        session.commit()
    return {"X-API-Key": raw_key}


def _profile_payload(ext: str = ".csv", **config_overrides: object) -> dict[str, object]:
    config: dict[str, object] = {
        "delimiter": ",",
        "columns": {
            "timestamp": "Timestamp",
            "result_value": "Result",
            "analyte": "Analyte",
            "qc_level": "Level",
            "instrument_id": "Instrument",
            "method_id": "Method",
            "control_material_lot": "Lot",
            "units": "Units",
        },
        "defaults": {"stream_id": "hba1c-arch"},
        "result_token_map": {"ND": {"numeric": 0.0, "qualifier": "non_detect"}},
    }
    config.update(config_overrides)
    return {
        "name": f"Architect {ext}",
        "profile_type": "delimited_direct",
        "status": "active",
        "file_extensions": [ext],
        "filename_patterns": [f"*{ext}"],
        "config": config,
    }


async def _create_profile(client: httpx.AsyncClient, payload: dict[str, object]) -> int:
    response = await client.post("/qc/import-profiles", json=payload, headers=AUTH_HEADERS)
    assert response.status_code == 200, response.text
    return int(response.json()["id"])


def _csv_row(result: str = "5.2", at_time: datetime | None = None) -> str:
    timestamp = (at_time or datetime.now(timezone.utc)).isoformat()
    return (
        "Timestamp,Result,Analyte,Level,Instrument,Method,Lot,Units\n"
        f"{timestamp},{result},HbA1c,Level 1,Architect,HPLC,LOT-001,%\n"
    )


@pytest.mark.anyio
async def test_supervisor_can_manage_profiles_but_analyst_cannot(client: httpx.AsyncClient) -> None:
    supervisor = _add_key("supervisor-import-key", Role.SUPERVISOR)
    analyst = _add_key("analyst-import-key", Role.QC_ANALYST)

    allowed = await client.post("/qc/import-profiles", json=_profile_payload(".csv"), headers=supervisor)
    assert allowed.status_code == 200, allowed.text
    denied = await client.post("/qc/import-profiles", json=_profile_payload(".txt"), headers=analyst)
    assert denied.status_code == 403


@pytest.mark.anyio
async def test_delimited_preview_apply_and_duplicate_idempotency(
    client: httpx.AsyncClient, tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("BAYESIANQC_IMPORT_ARCHIVE_ROOT", str(tmp_path))
    await _create_profile(client, _profile_payload(".csv"))
    data = _csv_row().encode()

    upload = await client.post(
        "/qc/imports",
        files={"file": ("architect.csv", data, "text/csv")},
        headers=AUTH_HEADERS,
    )
    assert upload.status_code == 200, upload.text
    body = upload.json()
    assert body["collector_action"] == "move_to_sent"
    assert body["batch"]["status"] == "ready_to_apply"
    assert body["batch"]["rows"][0]["status"] == "ready_to_apply"
    assert body["batch"]["rows"][0]["parsed_fields"]["result_raw_token"] == "5.2"
    assert tmp_path.joinpath(*body["batch"]["archived_path"].split("/")[-3:]).exists()

    applied = await client.post(f"/qc/imports/{body['batch']['id']}/apply", headers=AUTH_HEADERS)
    assert applied.status_code == 200, applied.text
    assert applied.json()["status"] == "applied"

    duplicate = await client.post(
        "/qc/imports",
        files={"file": ("architect.csv", data, "text/csv")},
        data={"auto_apply": "true"},
        headers=AUTH_HEADERS,
    )
    assert duplicate.status_code == 200, duplicate.text
    with Session(get_engine()) as session:
        records = session.exec(select(QCRecord).where(QCRecord.stream_id == "hba1c-arch")).all()
        assert len(records) == 1


@pytest.mark.anyio
async def test_bad_file_creates_failed_batch_and_collector_action(
    client: httpx.AsyncClient, tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("BAYESIANQC_IMPORT_ARCHIVE_ROOT", str(tmp_path))
    response = await client.post(
        "/qc/imports",
        files={"file": ("unknown.bad", b"not useful", "application/octet-stream")},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200, response.text
    batch = response.json()["batch"]
    assert batch["status"] == "failed_to_ingest"
    assert batch["collector_action"] == "move_to_failed"
    with Session(get_engine()) as session:
        stored = session.exec(select(ImportBatch)).one()
        assert stored.failure_reason


@pytest.mark.anyio
async def test_table_discovery_only_accepts_expected_analytes(client: httpx.AsyncClient) -> None:
    profile = _profile_payload(
        ".dat",
        delimiter=",",
        table_start="Results",
        analyte_column="Test",
        expected_tests=[{"name": "HbA1c", "aliases": ["HbA1c"]}],
        columns={
            "timestamp": "Timestamp",
            "result_value": "Value",
            "analyte": "Test",
            "qc_level": "Level",
            "instrument_id": "Instrument",
            "method_id": "Method",
            "control_material_lot": "Lot",
            "units": "Units",
        },
        defaults={"stream_id": "hba1c-arch"},
    )
    profile["profile_type"] = "instrument_table_discovery"
    await _create_profile(client, profile)
    timestamp = datetime.now(timezone.utc).isoformat()
    content = (
        "Instrument Export\nResults\n"
        "Test,Value,Timestamp,Level,Instrument,Method,Lot,Units\n"
        f"HbA1c,5.2,{timestamp},Level 1,Architect,HPLC,LOT-001,%\n"
        f"Glucose,100,{timestamp},Level 1,Architect,HPLC,LOT-001,mg/dL\n"
    ).encode()
    response = await client.post("/qc/imports", files={"file": ("run.dat", content, "text/plain")}, headers=AUTH_HEADERS)
    assert response.status_code == 200, response.text
    rows = response.json()["batch"]["rows"]
    assert [row["row_type"] for row in rows] == ["qc_result", "ignored"]


@pytest.mark.anyio
async def test_xlsx_xml_peak_and_collector_event_paths(client: httpx.AsyncClient, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BAYESIANQC_IMPORT_ARCHIVE_ROOT", str(tmp_path))
    await _create_profile(client, _profile_payload(".xlsx"))
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.append(["Timestamp", "Result", "Analyte", "Level", "Instrument", "Method", "Lot", "Units"])
    sheet.append([datetime.now(timezone.utc).isoformat(), "ND", "HbA1c", "Level 1", "Architect", "HPLC", "LOT-001", "%"])
    data = BytesIO()
    book.save(data)
    xlsx = await client.post(
        "/qc/imports",
        files={"file": ("run.xlsx", data.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=AUTH_HEADERS,
    )
    assert xlsx.status_code == 200, xlsx.text
    assert xlsx.json()["batch"]["rows"][0]["parsed_fields"]["result_qualifier"] == "non_detect"

    xml_columns = {
        "timestamp": "timestamp",
        "result_value": "result_value",
        "analyte": "analyte",
        "qc_level": "qc_level",
        "instrument_id": "instrument_id",
        "method_id": "method_id",
        "control_material_lot": "control_material_lot",
        "units": "units",
    }
    xml_profile = _profile_payload(".xml", columns=xml_columns)
    xml_profile["profile_type"] = "xml_mapping"
    xml_config = xml_profile["config"]
    assert isinstance(xml_config, dict)
    xml_config["rows_path"] = ".//Result"
    await _create_profile(client, xml_profile)
    xml = (
        "<Root><Result><timestamp>{0}</timestamp><result_value>5.2</result_value><analyte>HbA1c</analyte>"
        "<qc_level>Level 1</qc_level><instrument_id>Architect</instrument_id><method_id>HPLC</method_id>"
        "<control_material_lot>LOT-001</control_material_lot><units>%</units></Result></Root>"
    ).format(datetime.now(timezone.utc).isoformat())
    xml_response = await client.post("/qc/imports", files={"file": ("run.xml", xml, "application/xml")}, headers=AUTH_HEADERS)
    assert xml_response.status_code == 200, xml_response.text
    assert xml_response.json()["batch"]["ready_rows"] == 1

    peak_profile = _profile_payload(
        ".txt",
        peak_table=True,
        columns={"analyte": "Analyte", "peak_name": "Peak", "retention_time": "RT", "area": "Area", "height": "Height"},
    )
    await _create_profile(client, peak_profile)
    peaks = b"Analyte,Peak,RT,Area,Height\nHbA1c,A1c,1.23,456,78\n"
    peak_response = await client.post("/qc/imports", files={"file": ("peaks.txt", peaks, "text/plain")}, headers=AUTH_HEADERS)
    assert peak_response.status_code == 200, peak_response.text
    assert peak_response.json()["batch"]["peaks"][0]["peak_name"] == "A1c"
    with Session(get_engine()) as session:
        assert session.exec(select(InstrumentPeak)).one().area == 456

    event = await client.post(
        "/qc/collector/transfers/transfer-1/events",
        json={"event_type": "uploaded", "status": "ok", "source_path": "C:/runs/run.csv", "payload": {"hash": "abc"}},
        headers=AUTH_HEADERS,
    )
    assert event.status_code == 200, event.text
    with Session(get_engine()) as session:
        assert session.exec(select(CollectorTransferEvent)).one().transfer_id == "transfer-1"


@pytest.mark.anyio
async def test_ambiguous_backlog_match_stays_manual(client: httpx.AsyncClient) -> None:
    await _create_profile(client, _profile_payload(".csv"))
    due = datetime.now(timezone.utc) + timedelta(minutes=30)
    for _ in range(2):
        response = await client.post(
            "/qc/backlog",
            json={"source": "scheduled", "stream_id": "hba1c-arch", "due_at": due.isoformat()},
            headers=AUTH_HEADERS,
        )
        assert response.status_code == 200, response.text

    upload = await client.post(
        "/qc/imports",
        files={"file": ("ambiguous.csv", _csv_row(at_time=due).encode(), "text/csv")},
        headers=AUTH_HEADERS,
    )
    assert upload.status_code == 200, upload.text
    row = upload.json()["batch"]["rows"][0]
    assert row["status"] == "needs_review"
    assert row["warnings"] == ["backlog/run association is ambiguous"]
