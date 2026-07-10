export function formatCapaActions(rows: unknown[], stakeholder: boolean): string {
  if (!stakeholder) return JSON.stringify(rows ?? []);
  return (rows ?? []).map((row) => {
    if (!row || typeof row !== "object") return String(row);
    const record = row as Record<string, unknown>;
    return String(record.action ?? record.description ?? record.title ?? JSON.stringify(record));
  }).join("\n");
}

export function parseCapaActions(value: string, stakeholder: boolean): Record<string, unknown>[] {
  if (stakeholder) {
    return value.split("\n").map((item) => item.trim()).filter(Boolean).map((action) => ({ action }));
  }
  const parsed: unknown = JSON.parse(value);
  if (!Array.isArray(parsed)) throw new Error("Expected a JSON array");
  return parsed as Record<string, unknown>[];
}
