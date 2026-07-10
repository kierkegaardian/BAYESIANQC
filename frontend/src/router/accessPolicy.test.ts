import { describe, expect, it } from "vitest";
import { stakeholderRedirect } from "./accessPolicy";
import { appChildren } from "./appRoutes";

describe("stakeholder route access", () => {
  it("keeps explicitly visible demo and review surfaces accessible", () => {
    expect(stakeholderRedirect({ stakeholderDeployment: true, path: "/charts", stakeholderVisible: true })).toBeNull();
    expect(stakeholderRedirect({ stakeholderDeployment: true, path: "/kiosk/demo", stakeholderVisible: true })).toBeNull();
  });

  it("redirects operator plumbing without trapping the login route", () => {
    expect(stakeholderRedirect({ stakeholderDeployment: true, path: "/ingest", stakeholderVisible: false })).toBe("/");
    expect(stakeholderRedirect({ stakeholderDeployment: true, path: "/login", stakeholderVisible: false })).toBeNull();
  });

  it("does not constrain standard deployments", () => {
    expect(stakeholderRedirect({ stakeholderDeployment: false, path: "/ingest", stakeholderVisible: false })).toBeNull();
  });

  it("exposes only the intended stakeholder app routes", () => {
    const visible = appChildren
      .filter((route) => route.meta?.stakeholderVisible === true)
      .map((route) => route.path);
    expect(visible).toEqual(["", "backlog", "quarantine", "alerts", "investigations", "capas", "charts"]);
    expect(appChildren.find((route) => route.path === "ingest")?.meta?.stakeholderVisible).not.toBe(true);
    expect(appChildren.find((route) => route.path === "config/streams")?.meta?.stakeholderVisible).not.toBe(true);
  });
});
