from __future__ import annotations

import csv
import io
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.math.nig import beta_from_expected_sigma
from scripts.demo_kiosk.paths import FAMILIES, OUTPUT_ROOT
from scripts.demo_kiosk.scenarios import DemoScenario, scenario_for_stream

NOTICE = "Synthetic demo data only; not validated ASTM, manufacturer, clinical, pharmacological, or regulatory reference data."
CSV_FIELDS = [
    "stream_id",
    "result_value",
    "timestamp",
    "analyte",
    "qc_level",
    "instrument_id",
    "method_id",
    "operator_id",
    "reagent_lot",
    "control_material_lot",
    "calibration_status",
    "run_id",
    "units",
    "flags",
    "entry_source",
    "comments",
]

GROUPS: dict[str, dict[str, Any]] = {
    "fuel_astm": {
        "label": "Fuel ASTM Demo", "site": "Synthetic Fuels Lab", "start": "2026-02-02T08:00:00Z", "bench": "Fuels Bench",
        "groups": [
            ("OptiDist Fuel-01", "PAC", "OptiDist", "ASTM D86", "Atmospheric distillation", [("D86 IBP", "deg C", 76, 1.0, "Naphtha D86 QC"), ("D86 10% Recovered", "deg C", 92, 1.1, "Naphtha D86 QC"), ("D86 50% Recovered", "deg C", 121, 1.8, "Naphtha D86 QC"), ("D86 90% Recovered", "deg C", 168, 2.2, "Naphtha D86 QC")]),
            ("FlashCheck Fuel-02", "Eralytics", "ERAFLASH", "ASTM D93", "Flash point", [("Pensky Flash Point", "deg C", 62, 1.3, "Diesel flash QC"), ("Low Flash Solvent", "deg C", 25, 0.8, "Solvent flash QC"), ("Fire Point", "deg C", 88, 1.6, "Lube fire point QC")]),
            ("Sindie Fuel-03", "XOS", "Sindie", "ASTM D4294", "XRF sulfur", [("Total Sulfur", "mg/kg", 8, 0.8, "Gasoline sulfur QC"), ("ULSD Sulfur", "mg/kg", 4.5, 0.3, "Diesel sulfur QC"), ("Crude Sulfur", "% mass", 1.2, 0.05, "Crude sulfur QC")]),
            ("DensityPro Fuel-04", "Anton Paar", "DMA 4500", "ASTM D4052", "Digital density", [("Density 15C", "kg/m3", 742, 0.7, "Gasoline density QC"), ("API Gravity", "API", 58, 0.4, "Crude density QC"), ("Relative Density", "ratio", 0.82, 0.002, "Diesel density QC")]),
            ("ViscoBath Fuel-05", "Cannon", "CT-600", "ASTM D445", "Kinematic viscosity", [("Viscosity 40C", "cSt", 2.8, 0.05, "Diesel viscosity QC"), ("Viscosity 100C", "cSt", 8.9, 0.12, "Lube viscosity QC"), ("Viscosity Index", "index", 106, 1.5, "Lube VI QC")]),
            ("PourCloud Fuel-06", "PAC", "CPP 5Gs", "ASTM D97", "Low-temperature properties", [("Pour Point", "deg C", -18, 1.5, "Crude pour QC"), ("Cloud Point", "deg C", -8, 1.0, "Diesel cloud QC"), ("Cold Filter Plugging", "deg C", -12, 1.1, "Diesel CFPP QC")]),
            ("ColorScope Fuel-07", "Tintometer", "PFXi", "ASTM D1500", "Petroleum color", [("ASTM Color", "ASTM color", 1.5, 0.2, "Diesel color QC"), ("Saybolt Color", "Saybolt", 24, 0.8, "Kerosene color QC"), ("Haze Index", "index", 2.0, 0.25, "Finished fuel haze QC")]),
            ("VaporCheck Fuel-08", "Grabner", "Minivap", "ASTM D5191", "Vapor pressure", [("DVPE", "kPa", 62, 1.1, "Gasoline vapor QC"), ("RVP", "psi", 9.0, 0.2, "Gasoline RVP QC"), ("Vapor Liquid Ratio", "ratio", 20, 0.8, "V/L QC")]),
        ],
    },
    "medical_clinical": {
        "label": "Medical QC Demo", "site": "Synthetic Clinical Lab", "start": "2026-02-09T08:00:00Z", "bench": "Core Lab",
        "groups": [
            ("ChemMax C8000", "Abbott", "Architect", "Clinical Chemistry", "Photometric chemistry", [("Glucose", "mg/dL", 96, 2.0, "Chem L1"), ("Creatinine", "mg/dL", 1.1, 0.04, "Chem L1"), ("Sodium", "mmol/L", 140, 1.0, "Chem L2"), ("Potassium", "mmol/L", 4.2, 0.08, "Chem L2")]),
            ("A1cTrack H900", "Tosoh", "G8", "HbA1c HPLC", "Glycohemoglobin", [("HbA1c Low", "%", 5.4, 0.08, "A1c L1"), ("HbA1c High", "%", 9.1, 0.12, "A1c L2"), ("Fructosamine", "umol/L", 285, 7.0, "Glycemic marker QC")]),
            ("HemeFlow XN-20", "Sysmex", "XN", "CBC", "Hematology impedance", [("WBC", "10^3/uL", 6.2, 0.18, "CBC L1"), ("RBC", "10^6/uL", 4.6, 0.08, "CBC L1"), ("Hemoglobin", "g/dL", 13.5, 0.18, "CBC L2"), ("Platelets", "10^3/uL", 240, 7.0, "CBC L2")]),
            ("CoagStar CS-1", "Diagnostica", "CS", "Coagulation", "Optical clot", [("PT", "sec", 12.5, 0.25, "Coag L1"), ("INR", "ratio", 1.0, 0.03, "Coag L1"), ("aPTT", "sec", 31, 0.7, "Coag L2")]),
            ("ImmunoBright I200", "Roche", "Cobas e", "Immunoassay", "ECL immunoassay", [("TSH", "uIU/mL", 2.1, 0.07, "IA L1"), ("Free T4", "ng/dL", 1.2, 0.04, "IA L1"), ("Troponin I", "ng/L", 18, 1.2, "Cardiac QC"), ("Vitamin D", "ng/mL", 32, 1.5, "IA L2")]),
            ("GasLab ABL-90", "Radiometer", "ABL", "Blood Gas", "Electrochemical", [("pH", "pH", 7.4, 0.01, "Blood gas L1"), ("pCO2", "mmHg", 40, 1.0, "Blood gas L1"), ("Lactate", "mmol/L", 1.2, 0.06, "Blood gas L2")]),
            ("UriScan U500", "Arkray", "Aution", "Urinalysis", "Reflectance", [("Specific Gravity", "ratio", 1.02, 0.002, "Urine L1"), ("Urine Protein", "mg/dL", 15, 1.0, "Urine L2")]),
            ("Inflamark P200", "Thermo", "PCT", "Inflammation Panel", "Immunoturbidimetry", [("CRP", "mg/L", 3.0, 0.15, "Inflammation L1"), ("Procalcitonin", "ng/mL", 0.25, 0.02, "Inflammation L2")]),
        ],
    },
    "pharma_qc": {
        "label": "Pharma QC Demo", "site": "Synthetic Pharma QC", "start": "2026-02-16T08:00:00Z", "bench": "Pharma Bench",
        "groups": [
            ("HPLC Assay-01", "Waters", "Alliance", "HPLC Assay", "UV assay", [("API Potency", "% label", 100, 0.7, "Assay QC"), ("Preservative A", "mg/mL", 1.5, 0.03, "Assay QC"), ("Degradant Total", "% area", 0.4, 0.04, "Impurity QC"), ("Related Substance A", "% area", 0.12, 0.02, "Impurity QC")]),
            ("UPLC Impurity-02", "Waters", "Acquity", "UPLC Impurity", "Gradient impurity", [("Impurity B", "% area", 0.08, 0.015, "Impurity QC"), ("Impurity C", "% area", 0.11, 0.02, "Impurity QC"), ("Main Peak Purity", "%", 99.2, 0.12, "Purity QC"), ("Resolution R1", "USP", 2.5, 0.08, "System suitability")]),
            ("Dissolution DT-03", "Agilent", "708-DS", "Dissolution", "USP apparatus", [("Dissolution 15 min", "% dissolved", 42, 1.4, "Dissolution QC"), ("Dissolution 30 min", "% dissolved", 78, 1.8, "Dissolution QC"), ("Dissolution 45 min", "% dissolved", 92, 1.2, "Dissolution QC")]),
            ("KF Aqua-04", "Metrohm", "870 KF", "Karl Fischer", "Coulometric KF", [("Water Content", "%", 1.8, 0.06, "Moisture QC"), ("LOD", "%", 2.1, 0.08, "Moisture QC"), ("Residual Moisture", "ppm", 450, 18, "Moisture QC")]),
            ("Formulation Bench-05", "Mettler", "SevenExcellence", "Formulation", "pH osmolality", [("pH", "pH", 6.8, 0.03, "Formulation QC"), ("Osmolality", "mOsm/kg", 290, 4, "Formulation QC"), ("Conductivity", "uS/cm", 820, 18, "Formulation QC")]),
            ("LCMS Drug-06", "Sciex", "TripleQuad", "LC-MS Drug Panel", "MRM quantitation", [("Drug A Control", "ng/mL", 50, 2.0, "Drug panel L1"), ("Drug B Control", "ng/mL", 120, 4.0, "Drug panel L2"), ("Metabolite M1", "ng/mL", 35, 1.5, "Drug panel L1"), ("Internal Standard Area", "area ratio", 1.0, 0.04, "System suitability")]),
            ("TOC Clean-07", "Shimadzu", "TOC-L", "TOC", "Combustion TOC", [("TOC Rinse", "ppb", 60, 4, "Cleaning QC"), ("TOC WFI", "ppb", 180, 8, "Water QC")]),
            ("GC Solvent-08", "Agilent", "8890", "GC Residual Solvent", "Headspace GC", [("Residual Ethanol", "ppm", 1200, 45, "Residual solvent QC"), ("Residual Acetone", "ppm", 400, 20, "Residual solvent QC")]),
        ],
    },
    "steel_metals": {
        "label": "Steel Metals Demo", "site": "Synthetic Metals Lab", "start": "2026-02-23T08:00:00Z", "bench": "Metals Bench",
        "groups": [
            ("OES Spark-01", "SPECTRO", "MAXx", "OES Chemistry", "Spark OES", [("Carbon", "% mass", 0.18, 0.006, "Heat chemistry QC"), ("Manganese", "% mass", 1.25, 0.025, "Heat chemistry QC"), ("Silicon", "% mass", 0.28, 0.01, "Heat chemistry QC"), ("Chromium", "% mass", 0.85, 0.02, "Heat chemistry QC"), ("Nickel", "% mass", 0.35, 0.015, "Heat chemistry QC")]),
            ("CS Burn-02", "LECO", "CS844", "Combustion C/S", "Infrared combustion", [("Low Carbon", "% mass", 0.045, 0.002, "C/S QC"), ("Sulfur", "% mass", 0.018, 0.001, "C/S QC"), ("High Carbon", "% mass", 0.78, 0.012, "C/S QC")]),
            ("Hardness H-03", "Wilson", "Rockwell", "Hardness", "Indentation", [("Rockwell B", "HRB", 82, 1.0, "Hardness QC"), ("Rockwell C", "HRC", 34, 0.7, "Hardness QC"), ("Vickers HV10", "HV", 215, 4, "Hardness QC"), ("Brinell HBW", "HBW", 180, 3.5, "Hardness QC")]),
            ("Tensile T-04", "Instron", "5980", "Tensile", "Universal testing", [("Yield Strength", "MPa", 355, 6, "Tensile QC"), ("Ultimate Strength", "MPa", 520, 8, "Tensile QC"), ("Elongation", "%", 24, 0.8, "Tensile QC"), ("Reduction Area", "%", 48, 1.2, "Tensile QC")]),
            ("Impact I-05", "Zwick", "Charpy", "Charpy Impact", "Pendulum impact", [("Charpy 0C", "J", 85, 4, "Impact QC"), ("Charpy -20C", "J", 52, 3, "Impact QC"), ("Charpy Lateral", "mils", 35, 1.4, "Impact QC")]),
            ("CoatGauge C-06", "Fischer", "MMS", "Coating", "XRF coating", [("Zinc Coating", "g/m2", 275, 8, "Coating QC"), ("Tin Coating", "g/m2", 11.2, 0.4, "Coating QC"), ("Phosphate Weight", "g/m2", 2.4, 0.12, "Coating QC")]),
            ("MicroScope M-07", "Olympus", "GX53", "Metallography", "Image analysis", [("Grain Size", "ASTM No.", 7.5, 0.25, "Microstructure QC"), ("Inclusion Rating", "index", 1.0, 0.08, "Inclusion QC")]),
            ("FurnaceProbe F-08", "Datapaq", "DQ1860", "Furnace Profile", "Thermal profiling", [("Austenitizing Temp", "deg C", 845, 6, "Heat treat QC")]),
        ],
    },
}


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def write_outputs(*, check: bool = False) -> dict[str, int]:
    outputs = render_outputs()
    changed = [path for path, text in outputs.items() if not path.exists() or path.read_text(encoding="utf-8") != text]
    if check and changed:
        raise SystemExit("Demo kiosk fixtures are stale: " + ", ".join(str(path) for path in changed[:8]))
    if not check:
        for path, text in outputs.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
    return {"files": len(outputs), "changed": len(changed)}


def render_outputs() -> dict[Path, str]:
    outputs: dict[Path, str] = {}
    manifest: dict[str, Any] = {"synthetic_data_notice": NOTICE, "families": {}}
    layouts: dict[str, Any] = {"synthetic_data_notice": NOTICE, "families": {}}
    for family_id in FAMILIES:
        family_outputs, summary, panels = render_family(family_id, GROUPS[family_id])
        outputs.update(family_outputs)
        manifest["families"][family_id] = summary
        layouts["families"][family_id] = {"label": GROUPS[family_id]["label"], "panels": panels}
    outputs[OUTPUT_ROOT / "manifest.json"] = json_text(manifest)
    outputs[OUTPUT_ROOT / "kiosk_layouts.json"] = json_text(layouts)
    return outputs


def render_family(family_id: str, spec: dict[str, Any]) -> tuple[dict[Path, str], dict[str, int], list[dict[str, str]]]:
    base = datetime.fromisoformat(spec["start"].replace("Z", "+00:00"))
    assets = {"synthetic_data_notice": NOTICE, "instruments": [], "methods": [], "analytes": []}
    streams: list[dict[str, Any]] = []
    priors: list[dict[str, Any]] = []
    records: list[dict[str, str]] = []
    events: list[dict[str, Any]] = []
    actions = {"synthetic_data_notice": NOTICE, "family_id": family_id, "exclusions": [], "backlog": [], "quarantine_examples": []}
    panels: list[dict[str, str]] = []
    stream_index = 0
    for instrument, manufacturer, model, method, technique, analytes in spec["groups"]:
        assets["instruments"].append({"name": instrument, "manufacturer": manufacturer, "model": model, "site": spec["site"], "active": True})
        assets["methods"].append({"instrument_name": instrument, "name": method, "technique": technique, "active": True})
        for analyte, units, target, sigma, qc_level in analytes:
            stream_index += 1
            stream_id = f"demo-{family_id}-{slug(instrument)}-{slug(analyte)}"
            lot_a = f"{family_id[:3].upper()}-{stream_index:02d}-A"
            lot_b = f"{family_id[:3].upper()}-{stream_index:02d}-B"
            scenario = scenario_for_stream(stream_index)
            assets["analytes"].append({"instrument_name": instrument, "method_name": method, "name": analyte, "units": units, "active": True})
            streams.append(stream_config(stream_id, analyte, method, instrument, spec, qc_level, units, target, sigma, lot_a))
            priors.append(prior_config(stream_id, target, sigma, scenario))
            stream_records, marker = build_records(family_id, stream_index, stream_id, analyte, qc_level, instrument, method, units, target, sigma, lot_a, lot_b, base, scenario)
            records.extend(stream_records)
            events.extend(build_events(family_id, stream_id, instrument, analyte, method, lot_a, lot_b, base, stream_index, scenario))
            if len(panels) < 12:
                panels.append({"streamId": stream_id, "title": f"{analyte} - {instrument}", "start": base.date().isoformat(), "end": (base + timedelta(days=3)).date().isoformat(), "windowLabel": f"{base:%b %-d}-{(base + timedelta(days=3)):%-d}, 2026"})
            if stream_index in {1, 7, 13, 19}:
                actions["exclusions"].append({**marker, "reason": f"{family_id} demo excludes a known bad point"})
            if stream_index in {2, 8}:
                add_backlog_actions(actions, family_id, stream_id, analyte, qc_level, instrument, method, units, lot_a, target)
            if stream_index in {3, 9}:
                add_quarantine_actions(actions, family_id, stream_id, analyte, qc_level, instrument, method, units, lot_a, target)
    family_root = OUTPUT_ROOT / family_id
    outputs = {
        family_root / f"{family_id}_assets.json": json_text(assets),
        family_root / f"{family_id}_streams.json": json_text(streams),
        family_root / f"{family_id}_priors.json": json_text(priors),
        family_root / f"{family_id}_records.csv": csv_text(records),
        family_root / f"{family_id}_events.json": json_text(events),
        family_root / f"{family_id}_actions.json": json_text(actions),
    }
    return outputs, {"instruments": len(assets["instruments"]), "streams": len(streams), "records": len(records), "events": len(events)}, panels


def stream_config(stream_id: str, analyte: str, method: str, instrument: str, spec: dict[str, Any], qc_level: str, units: str, target: float, sigma: float, lot: str) -> dict[str, Any]:
    return {"stream_id": stream_id, "analyte": analyte, "method": method, "instrument": instrument, "site": spec["site"], "matrix": "Synthetic demo control material", "qc_level": qc_level, "control_material_lot": lot, "units": units, "target_value": target, "sigma": sigma, "warning_limit_sd": 2.0, "action_limit_sd": 3.0, "rule_set": {"rules": ["1-3s", "2-2s", "4-1s", "10x"]}, "min_value": round(target - 6 * sigma, 6), "max_value": round(target + 6 * sigma, 6), "risk_threshold_warn": 50, "risk_threshold_hold": 80, "bayes_warn_prob_threshold": 0.25, "bayes_warn_consecutive": 1, "bayes_hold_prob_threshold": 0.8, "bayes_hold_consecutive": 2, "effective_from": "2026-02-01T00:00:00Z"}


def prior_config(stream_id: str, target: float, sigma: float, scenario: DemoScenario) -> dict[str, Any]:
    if scenario.weak_prior:
        alpha = 1.25
        return {"stream_id": stream_id, "mu0": target, "kappa0": 0.35, "alpha0": alpha, "beta0": round(beta_from_expected_sigma(alpha, sigma), 6), "effective_from": "2026-02-01T00:00:00Z"}
    alpha = 2.0
    return {"stream_id": stream_id, "mu0": target, "kappa0": 1.0, "alpha0": alpha, "beta0": round(beta_from_expected_sigma(alpha, sigma), 6), "effective_from": "2026-02-01T00:00:00Z"}


def build_records(family_id: str, index: int, stream_id: str, analyte: str, qc_level: str, instrument: str, method: str, units: str, target: float, sigma: float, lot_a: str, lot_b: str, base: datetime, scenario: DemoScenario) -> tuple[list[dict[str, str]], dict[str, Any]]:
    rows: list[dict[str, str]] = []
    marker: dict[str, Any] = {}
    for point, z_value in enumerate(scenario.offsets, start=1):
        timestamp = base + timedelta(hours=(point - 1) * 2, minutes=(index % 6) * 5)
        value = round(target + z_value * sigma, 6)
        lot = lot_a if point <= 15 else lot_b
        run_id = f"{family_id}-{index:03d}-{point:03d}"
        row = {"stream_id": stream_id, "result_value": str(value), "timestamp": iso(timestamp), "analyte": analyte, "qc_level": qc_level, "instrument_id": instrument, "method_id": method, "operator_id": f"{family_id}-demo", "reagent_lot": f"{family_id[:3].upper()}-RG-{1 if point <= 15 else 2}", "control_material_lot": lot, "calibration_status": "ok", "run_id": run_id, "units": units, "flags": "[]", "entry_source": "manual", "comments": f"synthetic demo {scenario.label}"}
        rows.append(row)
        if point == scenario.marker_point:
            marker = {"stream_id": stream_id, "timestamp": row["timestamp"], "result_value": value, "run_id": run_id}
    return rows, marker


def build_events(family_id: str, stream_id: str, instrument: str, analyte: str, method: str, lot_a: str, lot_b: str, base: datetime, index: int, scenario: DemoScenario) -> list[dict[str, Any]]:
    minute = (index % 6) * 5
    common = {"stream_id": stream_id, "instrument_id": instrument, "analyte": analyte, "method_id": method}
    return [
        {"event_type": "calibration", "timestamp": iso(base - timedelta(minutes=30 - minute)), **common, "metadata": {"fixture": "demo-kiosk", "family": family_id, "note": "pre-run synthetic calibration"}},
        {"event_type": "control_material_lot_change", "timestamp": iso(base + timedelta(hours=30, minutes=minute)), **common, "metadata": {"fixture": "demo-kiosk", "family": family_id, "from": lot_a, "to": lot_b}},
        {"event_type": "maintenance", "timestamp": iso(base + timedelta(hours=42, minutes=minute)), **common, "metadata": {"fixture": "demo-kiosk", "family": family_id, "scenario": scenario.scenario_id, "note": scenario.event_note}},
    ]


def add_backlog_actions(actions: dict[str, Any], family_id: str, stream_id: str, analyte: str, qc_level: str, instrument: str, method: str, units: str, lot: str, target: float) -> None:
    for status, hours in [("open", -6), ("completed", -3)]:
        action_id = f"{family_id}:{stream_id}:{status}"
        action = {"action_id": action_id, "stream_id": stream_id, "due_offset_hours": hours, "status": status, "priority": "soon", "lab_bench": f"{family_id} demo bench", "assignment_group": f"{family_id} demo group", "assigned_to": None, "reference_material_label": qc_level, "notes": f"synthetic demo_action_id={action_id}", "requested_by": "demo-fixture-generator"}
        if status == "completed":
            action["completion_record"] = {"stream_id": stream_id, "result_value": round(target + 0.1, 6), "analyte": analyte, "qc_level": qc_level, "instrument_id": instrument, "method_id": method, "operator_id": "demo-backlog", "reagent_lot": f"{family_id[:3].upper()}-BACKLOG", "control_material_lot": lot, "calibration_status": "ok", "run_id": f"demo-backlog-{slug(stream_id)}", "units": units, "flags": [], "entry_source": "manual", "comments": f"completed synthetic scheduled QC for {family_id}"}
        actions["backlog"].append(action)


def add_quarantine_actions(actions: dict[str, Any], family_id: str, stream_id: str, analyte: str, qc_level: str, instrument: str, method: str, units: str, lot: str, target: float) -> None:
    base = {"stream_id": stream_id, "result_value": target, "analyte": analyte, "qc_level": qc_level, "instrument_id": instrument, "method_id": method, "operator_id": "demo-quarantine", "reagent_lot": f"{family_id[:3].upper()}-QUAR", "control_material_lot": lot, "calibration_status": "ok", "flags": [], "entry_source": "manual"}
    actions["quarantine_examples"].append({"action_id": f"{family_id}:{stream_id}:unit", "kind": "unit_mismatch", "payload": {**base, "run_id": f"demo-quarantine-unit-{slug(stream_id)}", "units": f"wrong-{units}", "comments": "synthetic unit mismatch quarantine"}})
    actions["quarantine_examples"].append({"action_id": f"{family_id}:{stream_id}:future", "kind": "future_timestamp", "payload": {**base, "run_id": f"demo-quarantine-future-{slug(stream_id)}", "units": units, "comments": "synthetic future timestamp quarantine"}})


def json_text(payload: Any) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def csv_text(rows: list[dict[str, str]]) -> str:
    handle = io.StringIO()
    writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return handle.getvalue()
