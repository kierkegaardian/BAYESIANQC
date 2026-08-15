import { describe, expect, it } from "vitest";
import type { StreamConfigOut } from "../api/contracts";
import {
  buildQcPayload,
  makeBatchRow,
  resetBatchRowForStream,
  validateManualRow,
  type ManualCommonFields,
} from "./ingestionWorkflow";

const stream: StreamConfigOut = {
  stream_id: "sulfur-l1",
  analyte: "Sulfur",
  method: "ASTM D7039",
  instrument: "Sindie",
  qc_level: "L1",
  control_material_lot: "LOT-1",
  units: "ppm",
  target_value: 10,
  sigma: 0.5,
  warning_limit_sd: 2,
  action_limit_sd: 3,
  control_limit_source: "configured",
  evaluation_reprocess_required: false,
  risk_threshold_warn: 50,
  risk_threshold_hold: 80,
  version: 1,
  effective_from: "2026-07-15T00:00:00Z",
  created_at: "2026-07-15T00:00:00Z",
  created_by: "test",
};

const common: ManualCommonFields = {
  timestamp: new Date("2026-07-15T01:00:00Z"),
  run_id: "run-1",
  entry_source: "manual",
  comments: "",
  idempotency_key: "",
  operator_id: "operator-1",
  reagent_lot: "R-1",
  calibration_status: "ok",
};

describe("manual QC measurement integrity", () => {
  it("starts every new row blank", () => {
    expect(makeBatchRow(stream, 1).result_value).toBeNull();
    expect(makeBatchRow(stream, 2, 42).result_value).toBeNull();
  });

  it("clears a prior measurement when the stream changes", () => {
    const row = makeBatchRow(stream, 1);
    row.result_value = 11.2;
    row.status = "accepted";
    row.message = "saved";
    resetBatchRowForStream(row);
    expect(row.result_value).toBeNull();
    expect(row.status).toBe("draft");
    expect(row.message).toBe("");
  });

  it("blocks missing and nonfinite results while accepting zero", () => {
    const row = makeBatchRow(stream, 1);
    expect(validateManualRow(row, stream, common.timestamp).errors).toContain("Enter a finite result.");
    row.result_value = Number.NaN;
    expect(validateManualRow(row, stream, common.timestamp).errors).toContain("Enter a finite result.");
    row.result_value = 0;
    expect(validateManualRow(row, stream, common.timestamp).errors).toEqual([]);
  });

  it("never substitutes the stream target in a payload", () => {
    const row = makeBatchRow(stream, 1);
    expect(() => buildQcPayload(row, stream, common)).toThrow("A finite result is required");
    row.result_value = 0;
    expect(buildQcPayload(row, stream, common).result_value).toBe(0);
  });
});
