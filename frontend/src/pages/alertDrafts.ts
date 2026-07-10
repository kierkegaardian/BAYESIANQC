import type { AlertOutWithQc, AlertStatus } from "../api/contracts";

export type AlertDraft = { status: AlertStatus; assigned_to: string };
export type AlertDraftMap = Record<string, AlertDraft>;

export function alertDraftFrom(row: AlertOutWithQc): AlertDraft {
  return { status: row.status ?? "open", assigned_to: row.assigned_to ?? "" };
}

export function ensureAlertDraft(drafts: AlertDraftMap, row: AlertOutWithQc): AlertDraft {
  return drafts[row.id] ??= alertDraftFrom(row);
}

export function resetAlertDraft(drafts: AlertDraftMap, row: AlertOutWithQc): AlertDraft {
  const reset = alertDraftFrom(row);
  drafts[row.id] = reset;
  return reset;
}

export function alertDraftChanged(drafts: AlertDraftMap, row: AlertOutWithQc): boolean {
  const draft = ensureAlertDraft(drafts, row);
  return draft.status !== row.status || draft.assigned_to !== (row.assigned_to ?? "");
}
