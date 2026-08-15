import { describe, expect, it } from "vitest";

import { buildSetupPayload, makeDraft } from "./datastreamSetup";

describe("datastream control limit payload", () => {
  it("preserves a fixed baseline range and effective date", () => {
    const draft = makeDraft();
    Object.assign(draft, {
      instrument_name: "Architect",
      method_name: "HPLC",
      parameter_name: "HbA1c",
      units: "%",
      material_name: "Control",
      control_material_lot: "LOT-1",
      control_limit_source: "fixed_baseline",
      baseline_start: "2026-01-01T00:00:00Z",
      baseline_end: "2026-01-31T00:00:00Z",
      effective_from: "2026-02-01T00:00:00Z",
    });

    const payload = buildSetupPayload(draft);
    expect(payload.control_limit_source).toBe("fixed_baseline");
    expect(payload.baseline_start).toBe("2026-01-01T00:00:00Z");
    expect(payload.baseline_end).toBe("2026-01-31T00:00:00Z");
    expect(payload.effective_from).toBe("2026-02-01T00:00:00Z");
  });

  it("removes stale baseline dates when configured limits are selected", () => {
    const draft = makeDraft();
    draft.control_limit_source = "configured";
    draft.baseline_start = "2026-01-01T00:00:00Z";
    draft.baseline_end = "2026-01-31T00:00:00Z";
    const payload = buildSetupPayload(draft);
    expect(payload.baseline_start).toBeNull();
    expect(payload.baseline_end).toBeNull();
  });
});
