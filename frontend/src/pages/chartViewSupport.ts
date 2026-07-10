import type { LotSegmentOut, QCEventOut, QCRecordChartOut } from "../api/contracts";

export function deriveLotSegments(records: QCRecordChartOut[]): LotSegmentOut[] {
  if (!records.length) return [];
  const segments: LotSegmentOut[] = [];
  let currentLot = records[0].control_material_lot || "unknown";
  let start = records[0].timestamp;
  let last = records[0].timestamp;
  let count = 0;
  for (const record of records) {
    const lot = record.control_material_lot || "unknown";
    if (lot !== currentLot) {
      segments.push({ control_material_lot: currentLot, start, end: last, count });
      currentLot = lot;
      start = record.timestamp;
      count = 0;
    }
    count += 1;
    last = record.timestamp;
  }
  segments.push({ control_material_lot: currentLot, start, end: last, count });
  return segments;
}

export function padSegmentEnd(start: string, end: string): string {
  if (start !== end) return end;
  return new Date(new Date(start).getTime() + 1000).toISOString();
}

export function formatEventLabel(event: QCEventOut): string {
  return String(event.event_type).replaceAll("_", " ");
}

export function startOfSelectedDay(date: Date): string {
  const copy = new Date(date);
  copy.setHours(0, 0, 0, 0);
  return copy.toISOString();
}

export function endOfSelectedDay(date: Date): string {
  const copy = new Date(date);
  copy.setHours(23, 59, 59, 999);
  return copy.toISOString();
}

export function parseSelectedDate(value: string | undefined): Date | null {
  if (!value) return null;
  const dateOnly = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (dateOnly) {
    const [, year, month, day] = dateOnly;
    return new Date(Number(year), Number(month) - 1, Number(day));
  }
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}
