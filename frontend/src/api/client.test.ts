import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(() => {
  vi.resetModules();
  vi.unstubAllGlobals();
});

function stubBrowser(): void {
  vi.stubGlobal("window", {
    location: { hostname: "localhost", protocol: "http:" },
    localStorage: { getItem: () => null, setItem: () => undefined, removeItem: () => undefined },
  });
}

describe("api.getPage", () => {
  it("reads total counts without changing the list response contract", async () => {
    stubBrowser();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response('[{"id":1}]', {
      status: 200,
      headers: { "Content-Type": "application/json", "X-Total-Count": "42" },
    })));
    const { api } = await import("./client");
    const page = await api.getPage<{ id: number }>("/alerts?limit=25&offset=25");
    expect(page).toEqual({ items: [{ id: 1 }], total: 42, limit: 25, offset: 25 });
  });

  it("falls back to the observed page extent when total-count is absent", async () => {
    stubBrowser();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response('[{"id":2},{"id":3}]', {
      status: 200,
      headers: { "Content-Type": "application/json" },
    })));
    const { api } = await import("./client");
    const page = await api.getPage<{ id: number }>("/alerts?limit=25&offset=25");
    expect(page.total).toBe(27);
  });

  it("allows a caller retry after a transient network failure", async () => {
    stubBrowser();
    const fetchMock = vi.fn()
      .mockRejectedValueOnce(new TypeError("offline"))
      .mockResolvedValueOnce(new Response('{"ok":true}', {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }));
    vi.stubGlobal("fetch", fetchMock);
    const { api } = await import("./client");
    await expect(api.get<{ ok: boolean }>("/health")).rejects.toThrow("offline");
    await expect(api.get<{ ok: boolean }>("/health")).resolves.toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
