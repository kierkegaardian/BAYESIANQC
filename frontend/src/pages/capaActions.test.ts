import { describe, expect, it } from "vitest";
import { formatCapaActions, parseCapaActions } from "./capaActions";

describe("stakeholder CAPA action fields", () => {
  it("serializes one action per line into structured API rows", () => {
    expect(parseCapaActions("Retrain operators\nReplace reagent lot\n", true)).toEqual([
      { action: "Retrain operators" },
      { action: "Replace reagent lot" },
    ]);
  });

  it("renders existing structured rows as editable plain text", () => {
    expect(formatCapaActions([{ action: "Retrain operators" }, { description: "Verify calibration" }], true))
      .toBe("Retrain operators\nVerify calibration");
  });

  it("preserves standard-mode JSON compatibility", () => {
    expect(parseCapaActions('[{"action":"Review"}]', false)).toEqual([{ action: "Review" }]);
  });
});
