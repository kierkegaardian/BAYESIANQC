import demoLayoutsJson from "../../../samples/demo_kiosk/kiosk_layouts.json";

export type KioskPanel = {
  streamId: string;
  title: string;
  start: string;
  end: string;
  windowLabel: string;
};

export type KioskLayout = {
  label: string;
  panels: KioskPanel[];
};

type DemoFamilyId = "fuel_astm" | "medical_clinical" | "pharma_qc" | "steel_metals";

type DemoLayoutsJson = {
  families: Record<DemoFamilyId, KioskLayout>;
};

const DEMO_LAYOUTS = (demoLayoutsJson as DemoLayoutsJson).families;
const DEMO_FAMILY_IDS: DemoFamilyId[] = ["fuel_astm", "medical_clinical", "pharma_qc", "steel_metals"];

export const BASE_KIOSK_PANELS: KioskPanel[] = [
  {
    streamId: "hba1c-kiosk",
    title: "HbA1c Control",
    start: "2026-01-05",
    end: "2026-01-06",
    windowLabel: "Jan 5-6, 2026",
  },
  {
    streamId: "d86-optidist-od1-ibp",
    title: "D86 OD-1 IBP",
    start: "2026-01-07",
    end: "2026-01-08",
    windowLabel: "Jan 7-8, 2026",
  },
  {
    streamId: "d86-optidist-od1-50pct",
    title: "D86 OD-1 50% Recovered",
    start: "2026-01-07",
    end: "2026-01-08",
    windowLabel: "Jan 7-8, 2026",
  },
  {
    streamId: "d86-optidist-od1-fbp",
    title: "D86 OD-1 FBP",
    start: "2026-01-07",
    end: "2026-01-08",
    windowLabel: "Jan 7-8, 2026",
  },
  {
    streamId: "d86-optidist-od2-ibp",
    title: "D86 OD-2 IBP",
    start: "2026-01-07",
    end: "2026-01-08",
    windowLabel: "Jan 7-8, 2026",
  },
  {
    streamId: "d86-optidist-od2-50pct",
    title: "D86 OD-2 50% Recovered",
    start: "2026-01-07",
    end: "2026-01-08",
    windowLabel: "Jan 7-8, 2026",
  },
  {
    streamId: "d86-optidist-od2-fbp",
    title: "D86 OD-2 FBP",
    start: "2026-01-07",
    end: "2026-01-08",
    windowLabel: "Jan 7-8, 2026",
  },
];

export const REFINERY_KIOSK_PANELS: KioskPanel[] = [
  {
    streamId: "refinery-optidist-naphtha-ibp",
    title: "Naphtha D86 IBP",
    start: "2026-01-09",
    end: "2026-01-10",
    windowLabel: "Jan 9-10, 2026",
  },
  {
    streamId: "refinery-optidist-naphtha-10pct",
    title: "Naphtha D86 10%",
    start: "2026-01-09",
    end: "2026-01-10",
    windowLabel: "Jan 9-10, 2026",
  },
  {
    streamId: "refinery-optidist-naphtha-50pct",
    title: "Naphtha D86 50%",
    start: "2026-01-09",
    end: "2026-01-10",
    windowLabel: "Jan 9-10, 2026",
  },
  {
    streamId: "refinery-optidist-naphtha-90pct",
    title: "Naphtha D86 90%",
    start: "2026-01-09",
    end: "2026-01-10",
    windowLabel: "Jan 9-10, 2026",
  },
  {
    streamId: "refinery-optidist-naphtha-fbp",
    title: "Naphtha D86 FBP",
    start: "2026-01-09",
    end: "2026-01-10",
    windowLabel: "Jan 9-10, 2026",
  },
  {
    streamId: "refinery-color-gasoline",
    title: "Gasoline Color",
    start: "2026-01-09",
    end: "2026-01-10",
    windowLabel: "Jan 9-10, 2026",
  },
  {
    streamId: "refinery-color-diesel",
    title: "Diesel Color",
    start: "2026-01-09",
    end: "2026-01-10",
    windowLabel: "Jan 9-10, 2026",
  },
  {
    streamId: "refinery-pour-crude",
    title: "Crude Blend Pour Point",
    start: "2026-01-09",
    end: "2026-01-10",
    windowLabel: "Jan 9-10, 2026",
  },
  {
    streamId: "refinery-sulfur-gasoline",
    title: "Gasoline Sulfur",
    start: "2026-01-09",
    end: "2026-01-10",
    windowLabel: "Jan 9-10, 2026",
  },
  {
    streamId: "refinery-sulfur-ulsd",
    title: "ULSD Sulfur",
    start: "2026-01-09",
    end: "2026-01-10",
    windowLabel: "Jan 9-10, 2026",
  },
];

const BASE_KIOSK_LAYOUT: KioskLayout = {
  label: "BayesianQC Kiosk",
  panels: BASE_KIOSK_PANELS,
};

const REFINERY_KIOSK_LAYOUT: KioskLayout = {
  label: "BayesianQC Refinery Kiosk",
  panels: REFINERY_KIOSK_PANELS,
};

const DEMO_KIOSK_LAYOUT: KioskLayout = {
  label: "BayesianQC Demo Kiosk",
  panels: DEMO_FAMILY_IDS.flatMap((familyId) => DEMO_LAYOUTS[familyId].panels.slice(0, 6)),
};

const DEMO_ROUTE_LAYOUTS: Record<string, KioskLayout> = {
  "/kiosk/demo": DEMO_KIOSK_LAYOUT,
  "/kiosk/fuel": DEMO_LAYOUTS.fuel_astm,
  "/kiosk/medical": DEMO_LAYOUTS.medical_clinical,
  "/kiosk/pharma": DEMO_LAYOUTS.pharma_qc,
  "/kiosk/steel": DEMO_LAYOUTS.steel_metals,
};

export function kioskLayoutForPath(path: string): KioskLayout {
  return staticKioskLayoutForPath(path) ?? BASE_KIOSK_LAYOUT;
}

export function staticKioskLayoutForPath(path: string): KioskLayout | null {
  if (path === "/kiosk/refinery") {
    return REFINERY_KIOSK_LAYOUT;
  }
  return DEMO_ROUTE_LAYOUTS[path] ?? (path === "/kiosk/charts" ? BASE_KIOSK_LAYOUT : null);
}
