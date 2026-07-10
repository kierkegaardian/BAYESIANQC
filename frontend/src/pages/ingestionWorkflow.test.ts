import { describe, expect, it } from "vitest";
import type { StreamConfigOut } from "../api/contracts";
import { buildQcPayload, makeBatchRow, type ManualCommonFields } from "./ingestionWorkflow";

const stream = {
  stream_id: "demo-stream",
  target_value: 100,
  sigma: 2,
  analyte: "Analyte",
  qc_level: "L1",
  instrument: "Instrument",
  method: "Method",
  control_material_lot: "LOT-1",
  units: "mg/L",
} as unknown as StreamConfigOut;
const common = {
  timestamp: new Date("2026-01-01T00:00:00Z"),
  run_id: "run-1",
  operator_id: "",
  reagent_lot: "",
  calibration_status: "",
  entry_source: "manual",
  comments: "",
  idempotency_key: "key-1",
} as ManualCommonFields;

describe("manual QC entry safety", () => {
  it("starts with a blank measured result", () => {
    expect(makeBatchRow(stream, 1).result_value).toBeNull();
  });

  it("never substitutes a target for a missing measurement", () => {
    const row = makeBatchRow(stream, 1);
    expect(() => buildQcPayload(row, stream, common)).toThrow("measured QC result");
    row.result_value = 0;
    expect(buildQcPayload(row, stream, common).result_value).toBe(0);
  });
});
