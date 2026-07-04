from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.demo_kiosk.actions import load_demo_actions
from scripts.demo_kiosk.paths import fixture_paths, parse_families
from scripts.kiosk_loader import (
    DEFAULT_ASSET_FILES,
    DEFAULT_EVENT_FILES,
    DEFAULT_PRIOR_FILES,
    DEFAULT_RECORD_FILES,
    DEFAULT_STREAM_FILES,
    ensure_assets,
    ensure_prior_configs,
    ensure_stream_configs,
    load_events,
    load_json_objects,
    load_records,
)


@dataclass(frozen=True)
class SelectedFixtures:
    assets: list[Path]
    streams: list[Path]
    priors: list[Path]
    records: list[Path]
    events: list[Path]
    actions: list[Path]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load deterministic chart-kiosk QC records and events.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8010", help="BayesianQC API base URL")
    parser.add_argument(
        "--api-key",
        default=os.getenv("BAYESIANQC_API_KEY", "local-dev-key"),
        help="API key with ingest permissions",
    )
    parser.add_argument(
        "--suite",
        choices=["existing", "demo", "all"],
        default="existing",
        help="Fixture suite to load; existing preserves the historical default",
    )
    parser.add_argument(
        "--families",
        help="Comma-separated demo families: fuel_astm,medical_clinical,pharma_qc,steel_metals",
    )
    parser.add_argument("--assets", type=Path, action="append", help="Instrument/method/analyte JSON fixture")
    parser.add_argument("--records", type=Path, action="append", help="QC record CSV fixture")
    parser.add_argument("--events", type=Path, action="append", help="QC event JSON fixture")
    parser.add_argument("--stream-config", type=Path, action="append", help="Stream config JSON fixture")
    parser.add_argument("--prior-config", type=Path, action="append", help="Prior config JSON fixture")
    parser.add_argument("--skip-assets", action="store_true", help="Do not create instruments/methods/analytes")
    parser.add_argument("--skip-events", action="store_true", help="Load only QC records")
    parser.add_argument("--skip-config", action="store_true", help="Assume the fixture stream already exists")
    parser.add_argument("--skip-actions", action="store_true", help="Skip demo exclusions, backlog, and quarantine examples")
    return parser.parse_args()


def selected_fixtures(args: argparse.Namespace) -> SelectedFixtures:
    families = parse_families(args.families)
    demo = fixture_paths(families)
    include_existing = args.suite in {"existing", "all"}
    include_demo = args.suite in {"demo", "all"}
    return SelectedFixtures(
        assets=args.assets or ([*DEFAULT_ASSET_FILES] if include_existing else []) + (demo.assets if include_demo else []),
        streams=args.stream_config or ([*DEFAULT_STREAM_FILES] if include_existing else []) + (demo.streams if include_demo else []),
        priors=args.prior_config or ([*DEFAULT_PRIOR_FILES] if include_existing else []) + (demo.priors if include_demo else []),
        records=args.records or ([*DEFAULT_RECORD_FILES] if include_existing else []) + (demo.records if include_demo else []),
        events=args.events or ([*DEFAULT_EVENT_FILES] if include_existing else []) + (demo.events if include_demo else []),
        actions=demo.actions if include_demo else [],
    )


def stream_ids_from_configs(paths: list[Path]) -> list[str]:
    return [
        str(payload.get("stream_id"))
        for path in paths
        for payload in load_json_objects(path)
        if payload.get("stream_id")
    ]


def load_suite(client: httpx.Client, fixtures: SelectedFixtures, args: argparse.Namespace) -> list[str]:
    if not args.skip_assets:
        print(f"Assets created: {ensure_assets(client, fixtures.assets)}")
    if args.skip_config:
        stream_ids = stream_ids_from_configs(fixtures.streams)
    else:
        stream_ids, created_streams = ensure_stream_configs(client, fixtures.streams)
        print(f"Streams loaded: {len(stream_ids)} ({created_streams} created)")
        print(f"Priors created: {ensure_prior_configs(client, fixtures.priors)}")
    accepted_records = sum(load_records(client, path) for path in fixtures.records)
    print(f"QC record responses accepted: {accepted_records}")
    if not args.skip_events:
        event_counts = [load_events(client, path) for path in fixtures.events]
        print(
            "QC events created: "
            f"{sum(created for created, _ in event_counts)}; "
            f"existing events skipped: {sum(skipped for _, skipped in event_counts)}"
        )
    if fixtures.actions:
        print(f"Demo actions: {load_demo_actions(client, fixtures.actions, skip_actions=args.skip_actions)}")
    return stream_ids


def main() -> None:
    args = parse_args()
    fixtures = selected_fixtures(args)
    headers = {"X-API-Key": args.api_key}
    with httpx.Client(base_url=args.base_url.rstrip("/"), headers=headers, timeout=30.0) as client:
        stream_ids = load_suite(client, fixtures, args)
    print(f"Open the UI chart route and select one of: {', '.join(stream_ids[:20])}")


if __name__ == "__main__":
    main()
