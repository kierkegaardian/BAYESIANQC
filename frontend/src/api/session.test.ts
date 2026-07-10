import { beforeEach, describe, expect, it, vi } from "vitest";

const apiGet = vi.hoisted(() => vi.fn());
vi.mock("./client", () => ({ api: { get: apiGet } }));

import {
  canApprove,
  canCommentQc,
  canIngestQc,
  canManageAlerts,
  canManageCapas,
  canManageInvestigations,
  canResolveQc,
  clearSessionUser,
  loadSessionUser,
} from "./session";

describe("workflow-specific session permissions", () => {
  beforeEach(() => {
    clearSessionUser();
    apiGet.mockReset();
  });

  it("allows stakeholder workflow actions without broad approval", async () => {
    apiGet.mockResolvedValue({
      role: "stakeholder",
      permissions: ["read", "resolve_qc", "manage_alerts", "manage_investigations", "manage_capas"],
    });
    await loadSessionUser();
    expect(canApprove.value).toBe(false);
    expect(canCommentQc.value).toBe(false);
    expect(canResolveQc.value).toBe(true);
    expect(canManageAlerts.value).toBe(true);
    expect(canManageInvestigations.value).toBe(true);
    expect(canManageCapas.value).toBe(true);
  });

  it("separates comment permission from ingestion", async () => {
    apiGet.mockResolvedValue({ role: "stakeholder", permissions: ["read", "comment_qc"] });
    await loadSessionUser();
    expect(canCommentQc.value).toBe(true);
    expect(canIngestQc.value).toBe(false);
  });
});
