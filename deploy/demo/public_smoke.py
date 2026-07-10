#!/usr/bin/env python3
from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from typing import Any


class SmokeFailure(RuntimeError):
    pass


BASE_URL = os.environ["JOSH_DEMO_URL"].rstrip("/")
TOKEN = base64.b64encode(
    f"josh:{os.environ['JOSH_DEMO_BASIC_PASSWORD']}".encode()
).decode()
AUTH_HEADERS = {"Authorization": f"Basic {TOKEN}"}


def request(
    path: str,
    *,
    method: str = "GET",
    expected: int = 200,
    payload: dict[str, Any] | None = None,
) -> bytes:
    body = None if method in {"GET", "HEAD"} else json.dumps(payload or {}).encode()
    request_headers = {**AUTH_HEADERS, "Content-Type": "application/json"}
    outgoing = urllib.request.Request(
        BASE_URL + path,
        data=body,
        headers=request_headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(outgoing, timeout=10) as response:
            status, data = response.status, response.read()
    except urllib.error.HTTPError as exc:
        status, data = exc.code, exc.read()
    if status != expected:
        raise SmokeFailure(
            f"{method} {path}: expected {expected}, got {status}: {data[:160]!r}"
        )
    return data


def read_json(path: str) -> Any:
    return json.loads(request(path))


def verify_reversible_alert_mutation() -> None:
    alerts = read_json("/api/alerts?status=open&limit=1")
    if not isinstance(alerts, list) or not alerts:
        raise SmokeFailure("fixture has no open alert for the reversible write smoke")
    alert_id = alerts[0].get("id")
    if not isinstance(alert_id, str) or not alert_id:
        raise SmokeFailure("open alert response lacks a string id")

    mutation_error: Exception | None = None
    try:
        updated = json.loads(
            request(
                f"/api/alerts/{alert_id}",
                method="PATCH",
                payload={
                    "status": "acknowledged",
                    "reason": "Josh demo public smoke reversible mutation",
                },
            )
        )
        if updated.get("status") != "acknowledged":
            raise SmokeFailure("alert mutation did not persist acknowledged status")
    except Exception as exc:  # restoration is mandatory even after an ambiguous response
        mutation_error = exc
    finally:
        try:
            restored = json.loads(
                request(
                    f"/api/alerts/{alert_id}",
                    method="PATCH",
                    payload={
                        "status": "open",
                        "reason": "Josh demo public smoke restore original alert status",
                    },
                )
            )
            if restored.get("status") != "open":
                raise SmokeFailure("alert restoration did not persist open status")
            final = read_json(f"/api/alerts/{alert_id}")
            if final.get("status") != "open":
                raise SmokeFailure("alert was not open after restoration readback")
        except Exception as restore_error:
            raise SmokeFailure(
                f"reversible alert smoke failed to restore {alert_id}: {restore_error}"
            ) from restore_error
    if mutation_error is not None:
        raise SmokeFailure(
            f"alert mutation failed but restoration succeeded: {mutation_error}"
        ) from mutation_error


def verify_path_bypasses_denied() -> None:
    for path in (
        "/api//qc/records",
        "/api/%71c/records",
        "/api/streams%2f..%2fqc%2frecords",
    ):
        outgoing = urllib.request.Request(
            BASE_URL + path,
            data=b"{}",
            headers={**AUTH_HEADERS, "Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(outgoing, timeout=10)
        except urllib.error.HTTPError as exc:
            if exc.code in (400, 403, 404):
                continue
            raise SmokeFailure(f"bypass probe {path} returned {exc.code}") from exc
        raise SmokeFailure(f"bypass probe unexpectedly succeeded: {path}")


def main() -> None:
    me = read_json("/api/me")
    if me.get("role") != "stakeholder":
        raise SmokeFailure(f"/api/me returned unexpected role: {me.get('role')!r}")
    for path in (
        "/api/stream-catalog",
        "/api/alerts",
        "/api/investigations",
        "/api/capas",
        "/api/reports/summary",
        "/api/qc/backlog",
        "/api/qc/quarantine",
        "/alerts",
    ):
        request(path)
    request("/api/streams", expected=403)
    if os.environ.get("JOSH_DEMO_MUTATE_ALERT") == "1":
        verify_reversible_alert_mutation()
    for path in ("/api/docs", "/api/openapi.json"):
        request(path, expected=404)
    for path in ("/api/qc/records", "/api/qc/imports", "/api/streams", "/api/instruments"):
        request(path, method="POST", expected=403)
    verify_path_bypasses_denied()


if __name__ == "__main__":
    main()
