import type { StreamSetupIn, StreamSetupPreviewOut } from "../api/contracts";

export type DatastreamDraft = {
  site: string;
  lab_bench: string;
  instrument_name: string;
  instrument_manufacturer: string;
  instrument_model: string;
  method_name: string;
  method_technique: string;
  parameter_name: string;
  units: string;
  material_name: string;
  material_manufacturer: string;
  matrix: string;
  qc_level: string;
  control_material_lot: string;
  stream_id: string;
  target_value: number;
  sigma: number;
  warning_limit_sd: number;
  action_limit_sd: number;
  min_value: number | null;
  max_value: number | null;
  config_reason: string;
  prior_mu0: number | null;
  prior_kappa0: number;
  prior_alpha0: number;
  prior_beta0: number | null;
  kiosk_enabled: boolean;
  kiosk_slug: string;
  kiosk_label: string;
  panel_title: string;
  panel_start: string;
  panel_end: string;
  panel_window_label: string;
};

export function makeDraft(): DatastreamDraft {
  return {
    site: "",
    lab_bench: "",
    instrument_name: "",
    instrument_manufacturer: "",
    instrument_model: "",
    method_name: "",
    method_technique: "",
    parameter_name: "",
    units: "",
    material_name: "",
    material_manufacturer: "",
    matrix: "",
    qc_level: "Level 1",
    control_material_lot: "",
    stream_id: "",
    target_value: 0,
    sigma: 0.1,
    warning_limit_sd: 2,
    action_limit_sd: 3,
    min_value: null,
    max_value: null,
    config_reason: "",
    prior_mu0: null,
    prior_kappa0: 1,
    prior_alpha0: 2,
    prior_beta0: null,
    kiosk_enabled: false,
    kiosk_slug: "",
    kiosk_label: "",
    panel_title: "",
    panel_start: "",
    panel_end: "",
    panel_window_label: "",
  };
}

export function slugify(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

export function generatedStreamId(draft: DatastreamDraft): string {
  return [
    draft.site,
    draft.lab_bench,
    draft.instrument_name,
    draft.method_name,
    draft.parameter_name,
    draft.qc_level,
    draft.control_material_lot,
  ]
    .map(slugify)
    .filter(Boolean)
    .join("-");
}

function optionalString(value: string): string | null {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function optionalNumber(value: number | null): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function buildSetupPayload(draft: DatastreamDraft): StreamSetupIn {
  const streamId = optionalString(draft.stream_id) ?? generatedStreamId(draft);
  const payload: StreamSetupIn = {
    stream_id: streamId,
    site: optionalString(draft.site),
    lab_bench: optionalString(draft.lab_bench),
    instrument_name: draft.instrument_name.trim(),
    instrument_manufacturer: optionalString(draft.instrument_manufacturer),
    instrument_model: optionalString(draft.instrument_model),
    method_name: draft.method_name.trim(),
    method_technique: optionalString(draft.method_technique),
    parameter_name: draft.parameter_name.trim(),
    units: draft.units.trim(),
    material_name: draft.material_name.trim(),
    material_manufacturer: optionalString(draft.material_manufacturer),
    matrix: optionalString(draft.matrix),
    qc_level: draft.qc_level.trim(),
    control_material_lot: draft.control_material_lot.trim(),
    target_value: draft.target_value,
    sigma: draft.sigma,
    warning_limit_sd: draft.warning_limit_sd,
    action_limit_sd: draft.action_limit_sd,
    min_value: optionalNumber(draft.min_value),
    max_value: optionalNumber(draft.max_value),
    risk_threshold_warn: 50,
    risk_threshold_hold: 80,
    bayes_warn_prob_threshold: 0.25,
    bayes_warn_consecutive: 1,
    bayes_hold_prob_threshold: 0.8,
    bayes_hold_consecutive: 2,
    config_reason: optionalString(draft.config_reason),
    prior_mu0: optionalNumber(draft.prior_mu0),
    prior_kappa0: draft.prior_kappa0,
    prior_alpha0: draft.prior_alpha0,
    prior_beta0: optionalNumber(draft.prior_beta0),
  };
  if (draft.kiosk_enabled) {
    payload.kiosk = {
      kiosk_slug: optionalString(draft.kiosk_slug) ?? slugify(draft.kiosk_label || streamId),
      kiosk_label: optionalString(draft.kiosk_label),
      panel_title: optionalString(draft.panel_title) ?? `${draft.parameter_name} - ${draft.instrument_name}`,
      panel_start: optionalString(draft.panel_start),
      panel_end: optionalString(draft.panel_end),
      panel_window_label: optionalString(draft.panel_window_label),
      mode: "both",
    };
  }
  return payload;
}

export function missingRequiredFields(draft: DatastreamDraft): string[] {
  return [
    ["Instrument", draft.instrument_name],
    ["Method", draft.method_name],
    ["Parameter", draft.parameter_name],
    ["Units", draft.units],
    ["Material", draft.material_name],
    ["QC level", draft.qc_level],
    ["Control lot", draft.control_material_lot],
  ]
    .filter(([, value]) => !String(value).trim())
    .map(([label]) => label);
}

export function validCanonicalRows(preview: StreamSetupPreviewOut | null): StreamSetupIn[] {
  return (preview?.rows ?? [])
    .filter((row) => row.valid && row.canonical)
    .map((row) => row.canonical as StreamSetupIn);
}
