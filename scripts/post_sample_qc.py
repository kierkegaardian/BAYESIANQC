#!/usr/bin/env python3
import argparse
from datetime import datetime, timezone

import httpx


def build_payload() -> dict:
    return {
        "stream_id": "hba1c-arch",
        "result_value": 6.0,
        "timestamp": datetime.now(timezone.utc).isoformat(),
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Post a sample QC record to the API.")
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8010",
        help="API base URL (default: http://127.0.0.1:8010)",
    )
    args = parser.parse_args()

    url = f"{args.base_url.rstrip('/')}/qc/records"
    payload = build_payload()

    with httpx.Client() as client:
        response = client.post(url, json=payload, timeout=10.0)

    print(f"POST {url}")
    print(f"Status: {response.status_code}")
    try:
        print(response.json())
    except ValueError:
        print(response.text)


if __name__ == "__main__":
    main()
