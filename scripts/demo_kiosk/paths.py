from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = ROOT / "samples" / "demo_kiosk"
LAYOUT_FILE = OUTPUT_ROOT / "kiosk_layouts.json"
MANIFEST_FILE = OUTPUT_ROOT / "manifest.json"
FAMILIES = ("fuel_astm", "medical_clinical", "pharma_qc", "steel_metals")


@dataclass(frozen=True)
class DemoFixturePaths:
    assets: list[Path]
    streams: list[Path]
    priors: list[Path]
    records: list[Path]
    events: list[Path]
    actions: list[Path]


def parse_families(value: str | None) -> list[str]:
    if not value:
        return list(FAMILIES)
    requested = [item.strip() for item in value.split(",") if item.strip()]
    unknown = sorted(set(requested) - set(FAMILIES))
    if unknown:
        raise SystemExit(f"Unknown demo kiosk families: {', '.join(unknown)}")
    return requested


def family_file(family_id: str, suffix: str) -> Path:
    return OUTPUT_ROOT / family_id / f"{family_id}_{suffix}"


def fixture_paths(families: list[str]) -> DemoFixturePaths:
    return DemoFixturePaths(
        assets=[family_file(family_id, "assets.json") for family_id in families],
        streams=[family_file(family_id, "streams.json") for family_id in families],
        priors=[family_file(family_id, "priors.json") for family_id in families],
        records=[family_file(family_id, "records.csv") for family_id in families],
        events=[family_file(family_id, "events.json") for family_id in families],
        actions=[family_file(family_id, "actions.json") for family_id in families],
    )
