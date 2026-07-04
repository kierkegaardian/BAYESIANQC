from __future__ import annotations

import csv
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import cast

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.db import get_engine
from app.db_models import QCRecord
from app.main import app
from scripts.load_chart_kiosk_suite import (
    DEFAULT_ASSET_FILES,
    DEFAULT_EVENT_FILES,
    DEFAULT_PRIOR_FILES,
    DEFAULT_RECORD_FILES,
    DEFAULT_STREAM_FILES,
    ensure_assets,
    ensure_prior_configs,
    ensure_stream_configs,
    load_events,
    load_records,
)

AUTH_HEADERS = {"X-API-Key": "local-dev-key"}
ROOT = Path(__file__).resolve().parents[1]
KIOSK_STREAM = ROOT / "samples" / "chart_kiosk_stream.json"
KIOSK_PRIOR = ROOT / "samples" / "chart_kiosk_prior.json"
KIOSK_RECORDS = ROOT / "samples" / "chart_kiosk_qc_records.csv"
KIOSK_EVENTS = ROOT / "samples" / "chart_kiosk_events.json"
KIOSK_ASSETS = ROOT / "samples" / "chart_kiosk_assets.json"
D86_STREAMS = ROOT / "samples" / "chart_kiosk_d86_streams.json"
D86_PRIORS = ROOT / "samples" / "chart_kiosk_d86_priors.json"
D86_RECORDS = ROOT / "samples" / "chart_kiosk_d86_records.csv"
D86_EVENTS = ROOT / "samples" / "chart_kiosk_d86_events.json"
REFINERY_RECORDS = ROOT / "samples" / "chart_kiosk_refinery_records.csv"


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def csv_record_count(path: Path) -> int:
    with path.open(newline="", encoding="utf-8") as handle:
        return sum(1 for _ in csv.DictReader(handle))


def read_json_object(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload
def read_json_objects(path: Path) -> list[dict[str, object]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        return [payload]
    assert isinstance(payload, list)
    assert all(isinstance(item, dict) for item in payload)
    return payload


async def load_kiosk_assets(client: httpx.AsyncClient) -> None:
    assets = read_json_object(KIOSK_ASSETS)
    instrument_ids: dict[str, int] = {}
    method_ids: dict[tuple[str, str], int] = {}

    for instrument in assets["instruments"]:  # type: ignore[index]
        response = await client.post("/instruments", json=instrument, headers=AUTH_HEADERS)
        assert response.status_code == 200
        instrument_ids[response.json()["name"]] = response.json()["id"]

    for method in assets["methods"]:  # type: ignore[index]
        payload = dict(method)
        instrument_name = str(payload.pop("instrument_name"))
        payload["instrument_id"] = instrument_ids[instrument_name]
        response = await client.post("/methods", json=payload, headers=AUTH_HEADERS)
        assert response.status_code == 200
        method_ids[(instrument_name, response.json()["name"])] = response.json()["id"]

    for analyte in assets["analytes"]:  # type: ignore[index]
        payload = dict(analyte)
        instrument_name = str(payload.pop("instrument_name"))
        method_name = str(payload.pop("method_name"))
        payload["method_id"] = method_ids[(instrument_name, method_name)]
        response = await client.post("/analytes", json=payload, headers=AUTH_HEADERS)
        assert response.status_code == 200


async def post_json_objects(client: httpx.AsyncClient, path: Path, endpoint: str) -> None:
    for payload in read_json_objects(path):
        response = await client.post(endpoint.format(stream_id=payload.get("stream_id")), json=payload, headers=AUTH_HEADERS)
        assert response.status_code == 200


async def upload_records(client: httpx.AsyncClient, path: Path) -> None:
    response = await client.post(
        "/qc/records/csv",
        files={"file": (path.name, path.read_bytes(), "text/csv")},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["accepted"] == csv_record_count(path)
    assert body["errors"] == []


async def load_kiosk_fixture(client: httpx.AsyncClient) -> None:
    await load_kiosk_assets(client)
    await post_json_objects(client, KIOSK_STREAM, "/streams")
    await post_json_objects(client, D86_STREAMS, "/streams")
    await post_json_objects(client, KIOSK_PRIOR, "/streams/{stream_id}/priors")
    await post_json_objects(client, D86_PRIORS, "/streams/{stream_id}/priors")
    await upload_records(client, KIOSK_RECORDS)
    await upload_records(client, D86_RECORDS)

    for event in [*read_json_objects(KIOSK_EVENTS), *read_json_objects(D86_EVENTS)]:
        response = await client.post("/qc/events", json=event, headers=AUTH_HEADERS)
        assert response.status_code == 200


@pytest.mark.anyio
async def test_chart_kiosk_fixture_exercises_chart_annotations(client: httpx.AsyncClient) -> None:
    await load_kiosk_fixture(client)

    with Session(get_engine()) as session:
        low_outlier = session.exec(select(QCRecord).where(QCRecord.run_id == "kiosk-run-014")).one()
        assert low_outlier.id is not None
        low_outlier_id = low_outlier.id

    resolution = await client.patch(
        f"/qc/records/{low_outlier_id}/resolution",
        json={
            "include_in_stats": False,
            "resolved_reason": "chart kiosk fixture excludes known low outlier",
        },
        headers=AUTH_HEADERS,
    )
    assert resolution.status_code == 200

    chart_response = await client.get(
        "/streams/hba1c-kiosk/chart"
        "?start=2026-01-05T00:00:00Z"
        "&end=2026-01-06T23:59:59Z"
        "&limit=100"
        "&include_evaluations=true",
        headers=AUTH_HEADERS,
    )
    assert chart_response.status_code == 200
    chart = chart_response.json()
    records = chart["records"]

    assert len(records) == csv_record_count(KIOSK_RECORDS)
    assert [segment["control_material_lot"] for segment in chart["lot_segments"]] == [
        "LOT-001",
        "LOT-002",
        "LOT-003",
    ]
    assert len(chart["events"]) == 4
    assert chart["alerts"]
    assert all(alert["qc_record_timestamp"] for alert in chart["alerts"])
    assert any(record["result_value"] > 5.95 for record in records)
    assert any(record["result_value"] < 4.45 for record in records)
    assert any(record["signals"] for record in records)
    included_risks = [
        record["bayesian_risk"]
        for record in records
        if record["include_in_stats"] is not False and record["bayesian_risk"] is not None
    ]
    assert included_risks
    assert all("probability_outside_limits" in risk for risk in included_risks)
    assert all("probability_outside_warning" in risk for risk in included_risks)

    resolved_record = next(record for record in records if record["id"] == low_outlier_id)
    assert resolved_record["include_in_stats"] is False
    assert resolved_record["resolved_reason"] == "chart kiosk fixture excludes known low outlier"
    assert resolved_record["bayesian_risk"] is None

    instrument_response = await client.get("/instruments", headers=AUTH_HEADERS)
    assert instrument_response.status_code == 200
    instrument_names = {instrument["name"] for instrument in instrument_response.json()}
    assert {"OptiDist OD-1", "OptiDist OD-2"} <= instrument_names

    d86_response = await client.get(
        "/streams/d86-optidist-od1-fbp/chart"
        "?start=2026-01-07T00:00:00Z"
        "&end=2026-01-08T23:59:59Z"
        "&limit=100"
        "&include_evaluations=true",
        headers=AUTH_HEADERS,
    )
    assert d86_response.status_code == 200
    d86_chart = d86_response.json()
    assert len(d86_chart["records"]) == 8
    assert len(d86_chart["events"]) == 2
    assert d86_chart["alerts"]
    assert [segment["control_material_lot"] for segment in d86_chart["lot_segments"]] == [
        "D86-STD-A",
        "D86-STD-B",
    ]
    assert any(record["result_value"] >= 209.0 for record in d86_chart["records"])


def test_chart_kiosk_loader_functions_are_idempotent(tmp_path: Path) -> None:
    with TestClient(app) as sync_client:
        sync_client.headers.update(AUTH_HEADERS)
        loader_client = cast(httpx.Client, sync_client)

        assert ensure_assets(loader_client, DEFAULT_ASSET_FILES) == {
            "instruments": 6,
            "methods": 6,
            "analytes": 14,
        }
        stream_ids, created_streams = ensure_stream_configs(loader_client, DEFAULT_STREAM_FILES)
        assert len(stream_ids) == 17
        assert created_streams == 17
        assert ensure_prior_configs(loader_client, DEFAULT_PRIOR_FILES) == 17
        assert sum(load_records(loader_client, path) for path in DEFAULT_RECORD_FILES) == 148
        with Session(get_engine()) as session:
            record_count = len(session.exec(select(QCRecord)).all())
        event_counts = [load_events(loader_client, path) for path in DEFAULT_EVENT_FILES]
        assert sum(created for created, _ in event_counts) == 36

        assert ensure_assets(loader_client, DEFAULT_ASSET_FILES) == {
            "instruments": 0,
            "methods": 0,
            "analytes": 0,
        }
        _, created_streams = ensure_stream_configs(loader_client, DEFAULT_STREAM_FILES)
        assert created_streams == 0
        assert ensure_prior_configs(loader_client, DEFAULT_PRIOR_FILES) == 0
        assert sum(load_records(loader_client, path) for path in DEFAULT_RECORD_FILES) == 148
        with Session(get_engine()) as session:
            assert len(session.exec(select(QCRecord)).all()) == record_count
        repeat_event_counts = [load_events(loader_client, path) for path in DEFAULT_EVENT_FILES]
        assert sum(created for created, _ in repeat_event_counts) == 0
        assert sum(skipped for _, skipped in repeat_event_counts) == 36

        case_asset = tmp_path / "case_assets.json"
        case_asset.write_text(
            json.dumps(
                {
                    "instruments": [{"name": "optidist od-1", "manufacturer": "PAC", "model": "OptiDist"}],
                    "methods": [
                        {"instrument_name": "optidist od-1", "name": "astm d86", "technique": "Atmospheric distillation"}
                    ],
                    "analytes": [
                        {"instrument_name": "optidist od-1", "method_name": "astm d86", "name": "d86 ibp", "units": "deg C"}
                    ],
                }
            ),
            encoding="utf-8",
        )
        assert ensure_assets(loader_client, [case_asset]) == {
            "instruments": 0,
            "methods": 0,
            "analytes": 0,
        }
        analyte_only_asset = tmp_path / "analyte_only_assets.json"
        analyte_only_asset.write_text(
            json.dumps(
                {
                    "analytes": [
                        {"instrument_name": "OptiDist OD-1", "method_name": "ASTM D86", "name": "D86 FBP", "units": "deg C"}
                    ]
                }
            ),
            encoding="utf-8",
        )
        assert ensure_assets(loader_client, [analyte_only_asset]) == {
            "instruments": 0,
            "methods": 0,
            "analytes": 0,
        }

        d86_response = loader_client.get(
            "/streams/d86-optidist-od2-fbp/chart"
            "?start=2026-01-07T00:00:00Z"
            "&end=2026-01-08T23:59:59Z"
            "&limit=100"
            "&include_evaluations=true"
        )
        assert d86_response.status_code == 200
        d86_chart = d86_response.json()
        assert len(d86_chart["records"]) == 8
        assert len(d86_chart["events"]) == 2
        assert len(d86_chart["lot_segments"]) == 2

        refinery_response = loader_client.get(
            "/streams/refinery-sulfur-ulsd/chart"
            "?start=2026-01-09T00:00:00Z"
            "&end=2026-01-10T23:59:59Z"
            "&limit=100"
            "&include_evaluations=true"
        )
        assert refinery_response.status_code == 200
        refinery_chart = refinery_response.json()
        assert len(refinery_chart["records"]) == 8
        assert len(refinery_chart["events"]) == 2
        assert [segment["control_material_lot"] for segment in refinery_chart["lot_segments"]] == [
            "REF-SUL-A",
            "REF-SUL-B",
        ]
        assert any(record["result_value"] >= 5.4 for record in refinery_chart["records"])
        assert any(record["signals"] for record in refinery_chart["records"])
        assert csv_record_count(REFINERY_RECORDS) == 80


def test_chart_kiosk_loader_reports_bad_flags_json(tmp_path: Path) -> None:
    bad_csv = tmp_path / "bad_records.csv"
    bad_csv.write_text("result_value,flags\n1.0,[bad\n", encoding="utf-8")
    with TestClient(app) as sync_client:
        sync_client.headers.update(AUTH_HEADERS)
        with pytest.raises(SystemExit, match="invalid flags JSON"):
            load_records(cast(httpx.Client, sync_client), bad_csv)
def test_chart_kiosk_loader_reports_bad_numeric_csv_data(tmp_path: Path) -> None:
    bad_csv = tmp_path / "bad_records.csv"
    bad_csv.write_text("result_value,flags\nnot-a-number,[]\n", encoding="utf-8")
    with TestClient(app) as sync_client:
        sync_client.headers.update(AUTH_HEADERS)
        with pytest.raises(SystemExit, match="invalid record data"):
            load_records(cast(httpx.Client, sync_client), bad_csv)
