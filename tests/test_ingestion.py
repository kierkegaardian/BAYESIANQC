from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
AUTH_HEADERS = {"X-API-Key": "local-dev-key"}


def _base_payload():
    now = datetime.now(timezone.utc)
    return {
        "stream_id": "hba1c-arch",
        "result_value": 6.0,
        "timestamp": now.isoformat(),
        "analyte": "HbA1c",
        "qc_level": "Level 1",
        "instrument_id": "Architect",
        "method_id": "HPLC",
        "operator_id": "tech1",
        "reagent_lot": "RL-001",
        "control_material_lot": "LOT-001",
        "calibration_status": "ok",
        "run_id": "run-123",
        "units": "%",
        "flags": [],
        "entry_source": "manual",
        "comments": "manual entry",
    }


def test_ingestion_rejects_missing_stream():
    payload = _base_payload()
    payload["stream_id"] = "unknown"
    response = client.post("/qc/records", json=payload, headers=AUTH_HEADERS)
    assert response.status_code == 404


def test_units_mismatch_rejected():
    payload = _base_payload()
    payload["units"] = "mmol/L"
    response = client.post("/qc/records", json=payload, headers=AUTH_HEADERS)
    assert response.status_code == 422


def test_action_signal_and_alert_created():
    payload = _base_payload()
    payload["result_value"] = 6.0
    response = client.post("/qc/records", json=payload, headers=AUTH_HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert body["qc"]["signals"][0]["rule"] == "1-3s"
    assert body["alert_created"] is not None
    assert body["qc"]["disposition"] == "reject"


def test_duplicate_detection():
    payload = _base_payload()
    payload["timestamp"] = (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat()
    response_first = client.post("/qc/records", json=payload, headers=AUTH_HEADERS)
    assert response_first.status_code == 200

    response_second = client.post("/qc/records", json=payload, headers=AUTH_HEADERS)
    assert response_second.status_code == 200
    assert response_second.json()["duplicate"] == "duplicate"


def test_manual_entry_audited():
    payload = _base_payload()
    payload["timestamp"] = (datetime.now(timezone.utc) + timedelta(seconds=2)).isoformat()
    payload["comments"] = "entered offline"
    response = client.post("/qc/records", json=payload, headers=AUTH_HEADERS)
    assert response.status_code == 200
    audit_response = client.get("/audit", headers=AUTH_HEADERS)
    assert audit_response.status_code == 200
    audit_entries = audit_response.json()
    assert any(entry["reason"] == "entered offline" for entry in audit_entries)
