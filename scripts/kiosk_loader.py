from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ASSET_FILES = [
    ROOT / "samples" / "chart_kiosk_assets.json",
    ROOT / "samples" / "chart_kiosk_refinery_assets.json",
]
DEFAULT_STREAM_FILES = [
    ROOT / "samples" / "chart_kiosk_stream.json",
    ROOT / "samples" / "chart_kiosk_d86_streams.json",
    ROOT / "samples" / "chart_kiosk_refinery_streams.json",
]
DEFAULT_PRIOR_FILES = [
    ROOT / "samples" / "chart_kiosk_prior.json",
    ROOT / "samples" / "chart_kiosk_d86_priors.json",
    ROOT / "samples" / "chart_kiosk_refinery_priors.json",
]
DEFAULT_RECORD_FILES = [
    ROOT / "samples" / "chart_kiosk_qc_records.csv",
    ROOT / "samples" / "chart_kiosk_d86_records.csv",
    ROOT / "samples" / "chart_kiosk_refinery_records.csv",
]
DEFAULT_EVENT_FILES = [
    ROOT / "samples" / "chart_kiosk_events.json",
    ROOT / "samples" / "chart_kiosk_d86_events.json",
    ROOT / "samples" / "chart_kiosk_refinery_events.json",
]


def clean_record(row: dict[str, str | None]) -> dict[str, Any]:
    payload: dict[str, Any] = {key: value for key, value in row.items() if value not in ("", None)}
    payload["result_value"] = float(payload["result_value"])
    if "flags" in payload:
        payload["flags"] = json.loads(str(payload["flags"]))
    return payload


def normalized_name(value: object) -> str:
    return str(value or "").strip().casefold()


def raise_api_error(response: httpx.Response) -> None:
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise SystemExit(f"{response.request.method} {response.request.url} failed: {response.text}") from exc


def load_records(client: httpx.Client, path: Path, *, idempotency_prefix: str = "chart-kiosk-suite") -> int:
    accepted = 0
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for index, row in enumerate(reader, start=1):
            try:
                payload = clean_record(row)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"{path}:{index} has invalid flags JSON: {row.get('flags')}") from exc
            except (KeyError, ValueError) as exc:
                raise SystemExit(f"{path}:{index} has invalid record data: {exc}") from exc
            run_id = payload.get("run_id") or f"row-{index}"
            stream_id = payload.get("stream_id") or "unknown-stream"
            response = client.post(
                "/qc/records",
                json=payload,
                headers={"Idempotency-Key": f"{idempotency_prefix}:{stream_id}:{run_id}"},
            )
            raise_api_error(response)
            accepted += int(response.json().get("status") == "accepted")
    return accepted


def load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"{path} must contain a JSON object")
    return payload


def load_json_objects(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        return [payload]
    if isinstance(payload, list) and all(isinstance(item, dict) for item in payload):
        return payload
    raise SystemExit(f"{path} must contain a JSON object or list of objects")


def ensure_assets(client: httpx.Client, paths: list[Path]) -> dict[str, int]:
    response = client.get("/instruments")
    raise_api_error(response)
    instruments_by_key = {normalized_name(item["name"]): int(item["id"]) for item in response.json()}
    created = {"instruments": 0, "methods": 0, "analytes": 0}
    methods_by_key: dict[tuple[str, str], int] = {}
    methods_by_instrument_id: dict[int, dict[str, int]] = {}
    analytes_by_method_id: dict[int, dict[str, int]] = {}

    def methods_for_instrument(instrument_id: int) -> dict[str, int]:
        if instrument_id not in methods_by_instrument_id:
            response = client.get("/methods", params={"instrument_id": instrument_id})
            raise_api_error(response)
            methods_by_instrument_id[instrument_id] = {
                normalized_name(item["name"]): int(item["id"]) for item in response.json()
            }
        return methods_by_instrument_id[instrument_id]

    def analytes_for_method(method_id: int) -> dict[str, int]:
        if method_id not in analytes_by_method_id:
            response = client.get("/analytes", params={"method_id": method_id})
            raise_api_error(response)
            analytes_by_method_id[method_id] = {
                normalized_name(item["name"]): int(item["id"]) for item in response.json()
            }
        return analytes_by_method_id[method_id]

    for path in paths:
        _ensure_asset_file(client, path, instruments_by_key, methods_by_key, methods_for_instrument, analytes_for_method, created)
    return created


def _ensure_asset_file(
    client: httpx.Client,
    path: Path,
    instruments_by_key: dict[str, int],
    methods_by_key: dict[tuple[str, str], int],
    methods_for_instrument: Any,
    analytes_for_method: Any,
    created: dict[str, int],
) -> None:
    asset_set = load_json_object(path)
    for instrument in asset_set.get("instruments", []):
        name = str(instrument.get("name") or "")
        if not name:
            raise SystemExit(f"{path} contains an instrument without name")
        key = normalized_name(name)
        if key not in instruments_by_key:
            response = client.post("/instruments", json=instrument)
            raise_api_error(response)
            instruments_by_key[key] = int(response.json()["id"])
            created["instruments"] += 1

    for method in asset_set.get("methods", []):
        method_payload = dict(method)
        instrument_name = str(method_payload.pop("instrument_name", ""))
        instrument_id = instruments_by_key.get(normalized_name(instrument_name))
        if instrument_id is None:
            raise SystemExit(f"{path} references unknown instrument {instrument_name!r}")
        existing = methods_for_instrument(instrument_id)
        method_name = str(method_payload.get("name") or "")
        method_key = normalized_name(method_name)
        if method_key not in existing:
            response = client.post("/methods", json={**method_payload, "instrument_id": instrument_id})
            raise_api_error(response)
            existing[method_key] = int(response.json()["id"])
            created["methods"] += 1
        methods_by_key[(normalized_name(instrument_name), normalized_name(method_name))] = existing[method_key]

    for analyte in asset_set.get("analytes", []):
        analyte_payload = dict(analyte)
        instrument_name = str(analyte_payload.pop("instrument_name", ""))
        method_name = str(analyte_payload.pop("method_name", ""))
        instrument_id = instruments_by_key.get(normalized_name(instrument_name))
        if instrument_id is None:
            raise SystemExit(f"{path} references unknown instrument {instrument_name!r}")
        method_id = methods_by_key.get((normalized_name(instrument_name), normalized_name(method_name)))
        if method_id is None:
            method_id = methods_for_instrument(instrument_id).get(normalized_name(method_name))
        if method_id is None:
            raise SystemExit(f"{path} references unknown method {instrument_name!r}/{method_name!r}")
        existing = analytes_for_method(method_id)
        analyte_name = str(analyte_payload.get("name") or "")
        analyte_key = normalized_name(analyte_name)
        if analyte_key not in existing:
            response = client.post("/analytes", json={**analyte_payload, "method_id": method_id})
            raise_api_error(response)
            existing[analyte_key] = int(response.json()["id"])
            created["analytes"] += 1


def ensure_stream_config(client: httpx.Client, payload: dict[str, Any]) -> tuple[str, bool]:
    stream_id = str(payload.get("stream_id") or "")
    if not stream_id:
        raise SystemExit("Stream config must include stream_id")
    response = client.get("/streams")
    raise_api_error(response)
    if any(stream.get("stream_id") == stream_id for stream in response.json()):
        return stream_id, False
    response = client.post("/streams", json=payload)
    raise_api_error(response)
    return stream_id, True


def ensure_prior_config(client: httpx.Client, stream_id: str, payload: dict[str, Any]) -> bool:
    response = client.get(f"/streams/{stream_id}/priors")
    raise_api_error(response)
    if any(prior_matches(prior, payload) for prior in response.json()):
        return False
    response = client.post(f"/streams/{stream_id}/priors", json=payload)
    raise_api_error(response)
    return True


def prior_matches(existing: dict[str, Any], payload: dict[str, Any]) -> bool:
    numeric_fields = ("mu0", "kappa0", "alpha0", "beta0")
    numeric_match = all(abs(float(existing[field]) - float(payload[field])) < 1e-12 for field in numeric_fields)
    return (
        str(existing.get("stream_id")) == str(payload.get("stream_id"))
        and numeric_match
        and normalized_timestamp(existing.get("effective_from")) == normalized_timestamp(payload.get("effective_from"))
    )


def ensure_stream_configs(client: httpx.Client, paths: list[Path]) -> tuple[list[str], int]:
    stream_ids: list[str] = []
    created = 0
    for path in paths:
        for payload in load_json_objects(path):
            stream_id, was_created = ensure_stream_config(client, payload)
            stream_ids.append(stream_id)
            created += int(was_created)
    return stream_ids, created


def ensure_prior_configs(client: httpx.Client, paths: list[Path]) -> int:
    created = 0
    for path in paths:
        for payload in load_json_objects(path):
            stream_id = str(payload.get("stream_id") or "")
            if not stream_id:
                raise SystemExit(f"{path} contains a prior without stream_id")
            created += int(ensure_prior_config(client, stream_id, payload))
    return created


def normalized_timestamp(value: object) -> str | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def event_key(event: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    return (
        event.get("stream_id"),
        event.get("event_type"),
        normalized_timestamp(event.get("timestamp")),
    )


def existing_event_keys(client: httpx.Client, stream_id: str) -> set[tuple[str | None, str | None, str | None]]:
    response = client.get("/qc/events", params={"stream_id": stream_id, "limit": 5000})
    raise_api_error(response)
    return {event_key(event) for event in response.json()}


def load_events(client: httpx.Client, path: Path) -> tuple[int, int]:
    events = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(events, list):
        raise SystemExit(f"{path} must contain a JSON list")

    keys_by_stream: dict[str, set[tuple[str | None, str | None, str | None]]] = {}
    created = 0
    skipped = 0
    for event in events:
        if not isinstance(event, dict):
            raise SystemExit(f"{path} contains a non-object event")
        stream_id = str(event.get("stream_id") or "")
        if not stream_id:
            raise SystemExit("Every kiosk event must include stream_id")
        keys = keys_by_stream.setdefault(stream_id, existing_event_keys(client, stream_id))
        key = event_key(event)
        if key in keys:
            skipped += 1
            continue
        response = client.post("/qc/events", json=event)
        raise_api_error(response)
        keys.add(key)
        created += 1
    return created, skipped
