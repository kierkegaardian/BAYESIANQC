from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

from scripts.kiosk_loader import load_json_object, normalized_timestamp, raise_api_error

ALL_BACKLOG_STATUSES = ("open", "in_progress", "completed", "canceled")


def load_demo_actions(client: httpx.Client, paths: list[Path], *, skip_actions: bool = False) -> dict[str, int]:
    if skip_actions:
        return {"excluded": 0, "backlog_created": 0, "backlog_completed": 0, "quarantined": 0}
    totals = {"excluded": 0, "backlog_created": 0, "backlog_completed": 0, "quarantined": 0}
    for path in paths:
        payload = load_json_object(path)
        for exclusion in payload.get("exclusions", []):
            totals["excluded"] += int(apply_exclusion(client, exclusion))
        for item in payload.get("backlog", []):
            created, completed = ensure_backlog_action(client, item)
            totals["backlog_created"] += int(created)
            totals["backlog_completed"] += int(completed)
        for example in payload.get("quarantine_examples", []):
            totals["quarantined"] += int(post_quarantine_example(client, example))
    return totals


def apply_exclusion(client: httpx.Client, action: dict[str, Any]) -> bool:
    record = find_chart_record(client, str(action["stream_id"]), str(action["timestamp"]), float(action["result_value"]))
    if record.get("include_in_stats") is False:
        return False
    response = client.patch(
        f"/qc/records/{record['id']}/resolution",
        json={"include_in_stats": False, "resolved_reason": str(action["reason"])},
    )
    raise_api_error(response)
    return True


def find_chart_record(client: httpx.Client, stream_id: str, timestamp: str, result_value: float) -> dict[str, Any]:
    parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    start = parsed.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1, seconds=-1)
    response = client.get(
        f"/streams/{stream_id}/chart",
        params={
            "start": normalized_timestamp(start),
            "end": normalized_timestamp(end),
            "limit": 500,
            "include_evaluations": "true",
        },
    )
    raise_api_error(response)
    for record in response.json().get("records", []):
        if normalized_timestamp(record.get("timestamp")) == normalized_timestamp(timestamp):
            if abs(float(record.get("result_value")) - result_value) < 1e-9:
                return record
    raise SystemExit(f"Could not find chart record for {stream_id} at {timestamp}")


def ensure_backlog_action(client: httpx.Client, action: dict[str, Any]) -> tuple[bool, bool]:
    existing = find_backlog_action(client, str(action["stream_id"]), str(action["action_id"]))
    created = False
    item = existing
    if item is None:
        response = client.post("/qc/backlog", json=backlog_payload(action))
        raise_api_error(response)
        item = response.json()
        created = True
    completed = False
    if action.get("status") == "completed" and item.get("status") != "completed":
        completion = dict(action["completion_record"])
        completion["timestamp"] = relative_timestamp(minutes=-1)
        completion["qc_backlog_item_id"] = item["id"]
        response = client.post(
            "/qc/records",
            json=completion,
            headers={"Idempotency-Key": f"demo-kiosk-backlog:{action['action_id']}"},
        )
        raise_api_error(response)
        completed = response.json().get("status") == "accepted"
    return created, completed


def find_backlog_action(client: httpx.Client, stream_id: str, action_id: str) -> dict[str, Any] | None:
    params = {"stream_id": stream_id, "limit": "500", "status": list(ALL_BACKLOG_STATUSES)}
    response = client.get("/qc/backlog", params=params)
    raise_api_error(response)
    marker = f"demo_action_id={action_id}"
    for row in response.json():
        if marker in str(row.get("notes") or ""):
            return row
    return None


def backlog_payload(action: dict[str, Any]) -> dict[str, Any]:
    due_at = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(hours=float(action["due_offset_hours"]))
    return {
        "source": "scheduled",
        "stream_id": action["stream_id"],
        "due_at": due_at.isoformat().replace("+00:00", "Z"),
        "priority": action["priority"],
        "lab_bench": action.get("lab_bench"),
        "assignment_group": action.get("assignment_group"),
        "assigned_to": action.get("assigned_to"),
        "reference_material_label": action.get("reference_material_label"),
        "notes": action.get("notes"),
        "requested_by": action.get("requested_by"),
    }


def post_quarantine_example(client: httpx.Client, example: dict[str, Any]) -> bool:
    payload = dict(example["payload"])
    payload["timestamp"] = relative_timestamp(minutes=10 if example.get("kind") == "future_timestamp" else -2)
    response = client.post(
        "/qc/records",
        json=payload,
        headers={"Idempotency-Key": f"demo-kiosk-quarantine:{example['action_id']}"},
    )
    raise_api_error(response)
    return response.json().get("status") == "quarantined"


def relative_timestamp(*, minutes: int) -> str:
    timestamp = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(minutes=minutes)
    return timestamp.isoformat().replace("+00:00", "Z")
