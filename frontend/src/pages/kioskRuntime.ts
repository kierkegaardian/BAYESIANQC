export type ChartMode = "results" | "risk" | "both";
export type KioskViewMode = "grid" | "single";

export function queryValue(value: unknown): string | undefined {
  if (Array.isArray(value)) {
    return typeof value[0] === "string" ? value[0] : undefined;
  }
  return typeof value === "string" ? value : undefined;
}

export function normalizeMode(value: unknown): ChartMode {
  const raw = queryValue(value);
  return raw === "results" || raw === "risk" || raw === "both" ? raw : "both";
}

export function normalizeView(value: unknown): KioskViewMode {
  return queryValue(value) === "single" ? "single" : "grid";
}

export function normalizeInterval(value: unknown): number {
  const parsed = Number(queryValue(value));
  if (!Number.isFinite(parsed)) {
    return 20;
  }
  return Math.min(300, Math.max(5, Math.round(parsed)));
}

export function normalizeTileCount(value: unknown): number {
  const parsed = Number(queryValue(value));
  if (!Number.isFinite(parsed)) {
    return 6;
  }
  return Math.min(12, Math.max(1, Math.round(parsed)));
}

export function requestedStreamIds(value: unknown): Set<string> | null {
  const raw = queryValue(value);
  if (!raw) {
    return null;
  }
  const ids = raw
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  return ids.length ? new Set(ids) : null;
}
