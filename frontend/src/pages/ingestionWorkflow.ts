import type {
  EntrySource,
  QCRecordChartOutEvaluated,
  QCRecordIn,
  StreamConfigOut,
} from "../api/contracts";

export type ManualCommonFields = {
  timestamp: Date;
  run_id: string;
  operator_id: string;
  reagent_lot: string;
  calibration_status: string;
  entry_source: EntrySource;
  comments: string;
  idempotency_key: string;
};

export type ManualBatchRow = {
  id: number;
  stream_id: string;
  result_value: number | null;
  comments: string;
  status: "draft" | "accepted" | "quarantined" | "error";
  message: string;
  qc_backlog_item_id?: number | null;
};

export type ValidationResult = {
  errors: string[];
  warnings: string[];
};

export type ManualRecentContext = {
  stream_id: string;
  run_id: string;
  operator_id: string;
  reagent_lot: string;
  calibration_status: string;
};

const RECENT_KEY = "bayesianqc.manualEntry.recent";

export function formatNumber(value: number | null | undefined, digits = 3): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return "-";
  }
  return Number(value).toFixed(digits).replace(/\.?0+$/, "");
}

export function formatDateTime(value: string): string {
  return new Date(value).toLocaleString();
}

export function formatPercent(value: number): string {
  return `${(Math.max(0, Math.min(1, value)) * 100).toFixed(1)}%`;
}

export function statusTagType(status: ManualBatchRow["status"]): "success" | "warning" | "danger" | "info" {
  if (status === "accepted") return "success";
  if (status === "quarantined") return "warning";
  if (status === "error") return "danger";
  return "info";
}

export function readManualRecent(storage: Storage): Partial<ManualRecentContext> | null {
  const raw = storage.getItem(RECENT_KEY);
  if (!raw) {
    return null;
  }
  try {
    const parsed = JSON.parse(raw) as Partial<ManualRecentContext>;
    return parsed && typeof parsed === "object" ? parsed : null;
  } catch {
    return null;
  }
}

export function writeManualRecent(storage: Storage, context: ManualRecentContext): void {
  storage.setItem(RECENT_KEY, JSON.stringify(context));
}

export function limitValue(stream: StreamConfigOut, sd: number, direction: -1 | 1): number {
  return Number(stream.target_value) + direction * sd * Number(stream.sigma);
}

export function matchingLevelStreams(streams: StreamConfigOut[], base: StreamConfigOut): StreamConfigOut[] {
  return streams
    .filter(
      (stream) =>
        stream.analyte === base.analyte &&
        stream.method === base.method &&
        stream.instrument === base.instrument &&
        stream.units === base.units
    )
    .sort((left, right) => left.qc_level.localeCompare(right.qc_level));
}

export function latestChartRecord(records: QCRecordChartOutEvaluated[]): QCRecordChartOutEvaluated | null {
  return records.length ? records[records.length - 1] : null;
}

export function makeBatchRow(stream: StreamConfigOut, id: number, backlogItemId: number | null = null): ManualBatchRow {
  return {
    id,
    stream_id: stream.stream_id,
    result_value: stream.target_value,
    comments: "",
    status: "draft",
    message: "",
    qc_backlog_item_id: backlogItemId,
  };
}

export function validateManualRow(
  row: ManualBatchRow,
  stream: StreamConfigOut | undefined,
  timestamp: Date,
  now = new Date()
): ValidationResult {
  const errors: string[] = [];
  const warnings: string[] = [];
  if (!stream) {
    errors.push("Select a stream.");
  }
  if (row.result_value === null || !Number.isFinite(row.result_value)) {
    errors.push("Enter a finite result.");
    return { errors, warnings };
  }
  if (!Number.isFinite(timestamp.getTime())) {
    errors.push("Enter a valid timestamp.");
  } else {
    const ageHours = (now.getTime() - timestamp.getTime()) / 3_600_000;
    if (timestamp.getTime() - now.getTime() > 5 * 60_000) {
      warnings.push("Timestamp is in the future.");
    }
    if (ageHours > 72) {
      warnings.push("Timestamp is more than 72 hours old.");
    }
  }
  if (!stream) {
    return { errors, warnings };
  }
  if (stream.min_value !== null && stream.min_value !== undefined && row.result_value < stream.min_value) {
    warnings.push(`Below configured minimum ${formatNumber(stream.min_value)}.`);
  }
  if (stream.max_value !== null && stream.max_value !== undefined && row.result_value > stream.max_value) {
    warnings.push(`Above configured maximum ${formatNumber(stream.max_value)}.`);
  }
  const warnLower = limitValue(stream, stream.warning_limit_sd, -1);
  const warnUpper = limitValue(stream, stream.warning_limit_sd, 1);
  const actionLower = limitValue(stream, stream.action_limit_sd, -1);
  const actionUpper = limitValue(stream, stream.action_limit_sd, 1);
  if (row.result_value < actionLower || row.result_value > actionUpper) {
    warnings.push("Outside action limits.");
  } else if (row.result_value < warnLower || row.result_value > warnUpper) {
    warnings.push("Outside warning limits.");
  }
  return { errors, warnings };
}

function optionalText(value: string): string | null {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

export function buildQcPayload(row: ManualBatchRow, stream: StreamConfigOut, common: ManualCommonFields): QCRecordIn {
  return {
    stream_id: stream.stream_id,
    result_value: row.result_value ?? stream.target_value,
    timestamp: new Date(common.timestamp).toISOString(),
    analyte: stream.analyte,
    qc_level: stream.qc_level,
    instrument_id: stream.instrument,
    method_id: stream.method,
    operator_id: optionalText(common.operator_id),
    reagent_lot: optionalText(common.reagent_lot),
    control_material_lot: stream.control_material_lot,
    calibration_status: optionalText(common.calibration_status),
    run_id: optionalText(common.run_id) ?? `ui-${Date.now()}`,
    units: stream.units,
    flags: [],
    entry_source: common.entry_source,
    comments: optionalText(row.comments) ?? optionalText(common.comments),
    qc_backlog_item_id: row.qc_backlog_item_id ?? null,
  };
}
