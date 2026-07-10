import { describe, expect, it } from "vitest";
import type { AlertOutWithQc } from "../api/contracts";
import { alertDraftChanged, ensureAlertDraft, resetAlertDraft, type AlertDraftMap } from "./alertDrafts";

const serverAlert = {
  id: "alert-1",
  status: "open",
  assigned_to: "analyst-a",
} as unknown as AlertOutWithQc;

describe("alert edit drafts", () => {
  it("keeps edits separate from the server row", () => {
    const drafts: AlertDraftMap = {};
    ensureAlertDraft(drafts, serverAlert).status = "closed";
    expect(serverAlert.status).toBe("open");
    expect(alertDraftChanged(drafts, serverAlert)).toBe(true);
  });

  it("rolls a failed save back to the last server values", () => {
    const drafts: AlertDraftMap = { "alert-1": { status: "closed", assigned_to: "analyst-b" } };
    expect(resetAlertDraft(drafts, serverAlert)).toEqual({ status: "open", assigned_to: "analyst-a" });
    expect(alertDraftChanged(drafts, serverAlert)).toBe(false);
  });
});
