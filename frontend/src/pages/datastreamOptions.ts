import { api } from "../api/client";
import type {
  AnalyteOut,
  ControlMaterialOut,
  EnterpriseSiteOut,
  InstrumentOut,
  KioskLayoutOut,
  LabAreaOut,
  MethodOut,
} from "../api/contracts";

export type ConfigCreateKind = "site" | "area" | "instrument" | "test" | "analyte" | "material";

function qs(values: Record<string, string | number | boolean | null | undefined>): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) {
    if (value !== null && value !== undefined && value !== "") {
      params.set(key, String(value));
    }
  }
  const query = params.toString();
  return query ? `?${query}` : "";
}

export async function loadSites(): Promise<EnterpriseSiteOut[]> {
  return api.get<EnterpriseSiteOut[]>("/enterprise-sites?active=true");
}

export async function loadAreas(siteId: number | null): Promise<LabAreaOut[]> {
  return api.get<LabAreaOut[]>(`/lab-areas${qs({ active: true, site_id: siteId })}`);
}

export async function loadInstruments(siteId: number | null, areaId: number | null): Promise<InstrumentOut[]> {
  return api.get<InstrumentOut[]>(`/instruments${qs({ active: true, site_id: siteId, lab_area_id: areaId })}`);
}

export async function loadMethods(instrumentId: number | null): Promise<MethodOut[]> {
  return api.get<MethodOut[]>(`/methods${qs({ active: true, instrument_id: instrumentId })}`);
}

export async function loadAnalytes(methodId: number | null): Promise<AnalyteOut[]> {
  return api.get<AnalyteOut[]>(`/analytes${qs({ active: true, method_id: methodId })}`);
}

export async function loadMaterials(): Promise<ControlMaterialOut[]> {
  return api.get<ControlMaterialOut[]>("/control-materials?active=true");
}

export async function loadKiosks(site: string, labBench: string): Promise<KioskLayoutOut[]> {
  return api.get<KioskLayoutOut[]>(`/kiosks${qs({ active: true, site, lab_bench: labBench })}`);
}

export function instrumentLabel(row: InstrumentOut): string {
  return [row.name, row.model].filter(Boolean).join(" / ");
}

export function methodLabel(row: MethodOut): string {
  return [row.name, row.technique].filter(Boolean).join(" / ");
}

export function analyteLabel(row: AnalyteOut): string {
  return [row.name, row.units].filter(Boolean).join(" / ");
}

export function materialLabel(row: ControlMaterialOut): string {
  return [row.name, row.qc_level, row.lot].filter(Boolean).join(" / ");
}
