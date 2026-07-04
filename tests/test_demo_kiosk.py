from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import cast

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from scripts.demo_kiosk import generator
from scripts.demo_kiosk.generator import write_outputs
from scripts.demo_kiosk.paths import FAMILIES, LAYOUT_FILE, MANIFEST_FILE, fixture_paths
from scripts.load_chart_kiosk_suite import load_suite, selected_fixtures

AUTH_HEADERS = {"X-API-Key": "local-dev-key"}
ROOT = Path(__file__).resolve().parents[1]


def csv_count(path: Path) -> int:
    with path.open(newline="", encoding="utf-8") as handle:
        return sum(1 for _ in csv.DictReader(handle))


def test_demo_kiosk_generated_fixtures_are_current_and_balanced() -> None:
    write_outputs(check=True)
    manifest = json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
    assert manifest["synthetic_data_notice"].startswith("Synthetic demo data only")
    assert set(manifest["families"]) == set(FAMILIES)
    assert sum(family["instruments"] for family in manifest["families"].values()) == 32
    assert sum(family["streams"] for family in manifest["families"].values()) == 100
    assert sum(family["records"] for family in manifest["families"].values()) == 2500
    assert sum(family["events"] for family in manifest["families"].values()) == 300
    assert all(csv_count(path) == 625 for path in fixture_paths(list(FAMILIES)).records)
    fuel_root = ROOT / "samples" / "demo_kiosk" / "fuel_astm"
    configs = {
        stream["stream_id"]: stream
        for stream in json.loads((fuel_root / "fuel_astm_streams.json").read_text(encoding="utf-8"))
    }
    patterns: dict[str, list[float]] = {}
    comments: set[str] = set()
    with (fuel_root / "fuel_astm_records.csv").open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            config = configs[row["stream_id"]]
            z_score = (float(row["result_value"]) - float(config["target_value"])) / float(config["sigma"])
            patterns.setdefault(row["stream_id"], []).append(round(z_score, 1))
            comments.add(row["comments"])
    first_panel_patterns = list(patterns.values())[:12]
    assert len({tuple(pattern[:13]) for pattern in first_panel_patterns}) >= 10
    assert any(max(abs(value) for value in pattern) < 0.5 for pattern in first_panel_patterns)
    assert any("low Bayesian confidence" in comment for comment in comments)
    assert any("R-4s precision failure" in comment for comment in comments)


def test_demo_kiosk_check_detects_generated_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    outputs = generator.render_outputs()
    stale_path = MANIFEST_FILE
    monkeypatch.setattr(generator, "render_outputs", lambda: {stale_path: outputs[stale_path] + "\n"})
    with pytest.raises(SystemExit, match="stale"):
        generator.write_outputs(check=True)


def test_demo_kiosk_loader_seeds_actions_and_sentinel_chart() -> None:
    args = argparse.Namespace(
        suite="demo",
        families="fuel_astm",
        assets=None,
        records=None,
        events=None,
        stream_config=None,
        prior_config=None,
        skip_assets=False,
        skip_events=False,
        skip_config=False,
        skip_actions=False,
    )
    fixtures = selected_fixtures(args)
    assert len(fixtures.records) == 1

    with TestClient(app) as sync_client:
        sync_client.headers.update(AUTH_HEADERS)
        loader_client = cast(httpx.Client, sync_client)
        stream_ids = load_suite(loader_client, fixtures, args)
        assert len(stream_ids) == 25

        chart = loader_client.get(
            "/streams/demo-fuel_astm-optidist-fuel-01-d86-ibp/chart",
            params={
                "start": "2026-02-02T00:00:00Z",
                "end": "2026-02-05T23:59:59Z",
                "limit": 100,
                "include_evaluations": "true",
            },
        )
        assert chart.status_code == 200
        body = chart.json()
        assert len(body["records"]) == 25
        assert len(body["events"]) == 3
        assert len(body["lot_segments"]) == 2
        assert any(record["signals"] for record in body["records"])
        assert any(record["include_in_stats"] is False for record in body["records"])

        backlog = loader_client.get(
            "/qc/backlog",
            params=[("status", "open"), ("status", "completed"), ("stream_id", stream_ids[1]), ("limit", "20")],
        )
        assert backlog.status_code == 200
        rows = backlog.json()
        assert {row["status"] for row in rows} >= {"open", "completed"}

        quarantine = loader_client.get("/qc/quarantine")
        assert quarantine.status_code == 200
        reasons = {row["reason"] for row in quarantine.json()}
        assert {"unit_mismatch", "suspicious_timestamp"} <= reasons


def test_demo_kiosk_routes_and_layouts_are_registered() -> None:
    router_text = (ROOT / "frontend" / "src" / "router" / "index.ts").read_text(encoding="utf-8")
    layout_text = (ROOT / "frontend" / "src" / "components" / "AppLayout.vue").read_text(encoding="utf-8")
    panels_text = (ROOT / "frontend" / "src" / "pages" / "kioskPanels.ts").read_text(encoding="utf-8")
    kiosk_text = (ROOT / "frontend" / "src" / "pages" / "ChartKiosk.vue").read_text(encoding="utf-8")
    chart_text = (ROOT / "frontend" / "src" / "pages" / "ChartView.vue").read_text(encoding="utf-8")
    tile_text = (ROOT / "frontend" / "src" / "pages" / "KioskChartTile.vue").read_text(encoding="utf-8")
    runtime_text = (ROOT / "frontend" / "src" / "pages" / "kioskRuntime.ts").read_text(encoding="utf-8")
    layouts = json.loads(LAYOUT_FILE.read_text(encoding="utf-8"))
    for route in ["/kiosk/demo", "/kiosk/fuel", "/kiosk/medical", "/kiosk/pharma", "/kiosk/steel"]:
        assert f'path: "{route}"' in router_text
        assert f'index="{route}"' in layout_text
    assert 'path: "kiosks"' in router_text
    assert 'index="/kiosks"' in layout_text
    assert (ROOT / "frontend" / "src" / "pages" / "KioskBuilder.vue").exists()
    assert 'index="/kiosk/refinery"' in layout_text
    assert 'index="/kiosk/charts"' in layout_text
    for family in FAMILIES:
        assert len(layouts["families"][family]["panels"]) == 12
    assert "kioskLayoutForPath" in panels_text
    assert "KioskChartTile" in kiosk_text
    assert '@open-single="openSingleStream"' in kiosk_text
    assert "openGridView" in kiosk_text
    assert "loadSessionUser" in kiosk_text
    assert '"open-single": [streamId: string]' in tile_text
    assert "QC Point Detail" in chart_text
    assert 'appendTo: "body"' in chart_text
    assert "showSymbol: isKiosk.value" in chart_text
    assert 'queryValue(value) === "single"' in runtime_text
    assert "return 6" in runtime_text
