import type { RouteRecordRaw } from "vue-router";

const ChartKiosk = () => import("../pages/ChartKiosk.vue");

function kioskRoute(path: string, title: string, helpText: string): RouteRecordRaw {
  return {
    path,
    component: ChartKiosk,
    meta: {
      hideHelp: true,
      helpTitle: title,
      helpText,
      requiredPermission: "read",
      stakeholderVisible: true,
    },
  };
}

export const kioskRoutes: RouteRecordRaw[] = [
  kioskRoute("/kiosk/charts", "Chart Kiosk", "Displays the seeded base QC chart streams."),
  kioskRoute("/kiosk/refinery", "Refinery Kiosk", "Displays the synthetic refinery QC streams."),
  kioskRoute("/kiosk/demo", "Demo Kiosk", "Displays representative synthetic fuel, medical, pharma, and steel QC streams."),
  kioskRoute("/kiosk/fuel", "Fuel ASTM Kiosk", "Displays synthetic fuel and ASTM-style QC demo streams."),
  kioskRoute("/kiosk/medical", "Medical Kiosk", "Displays synthetic clinical laboratory QC demo streams."),
  kioskRoute("/kiosk/pharma", "Pharma QC Kiosk", "Displays synthetic pharmaceutical QC demo streams."),
  kioskRoute("/kiosk/steel", "Steel Kiosk", "Displays synthetic steel and metals QC demo streams."),
  kioskRoute("/kiosk/:slug", "Saved Kiosk", "Displays a saved kiosk layout."),
];
