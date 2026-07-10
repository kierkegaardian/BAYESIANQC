import type { RouteRecordRaw } from "vue-router";

const page = (name: string) => () => import(`../pages/${name}.vue`);

export const appChildren: RouteRecordRaw[] = [
  {
    path: "",
    component: page("Dashboard"),
    meta: {
      helpTitle: "Dashboard",
      helpText: "Review active workflow counts and open a synthetic demonstration scenario.",
      requiredPermission: "read",
      stakeholderVisible: true,
    },
  },
  {
    path: "backlog",
    component: page("Backlog"),
    meta: {
      helpTitle: "QC Backlog",
      helpText: "Review scheduled or requested QC work by instrument, bench, group, or assignee.",
      requiredPermission: "read",
      stakeholderVisible: true,
    },
  },
  {
    path: "quarantine",
    component: page("Quarantine"),
    meta: {
      helpTitle: "Quarantine",
      helpText: "Review rows preserved before ingestion and their review decisions.",
      requiredPermission: "read",
      stakeholderVisible: true,
    },
  },
  {
    path: "alerts",
    component: page("Alerts"),
    meta: {
      helpTitle: "Alerts",
      helpText: "Review QC alerts and, when permitted, record status and assignment decisions.",
      requiredPermission: "read",
      stakeholderVisible: true,
    },
  },
  {
    path: "investigations",
    component: page("Investigations"),
    meta: {
      helpTitle: "Investigations",
      helpText: "Review investigations linked to QC alerts.",
      requiredPermission: "read",
      stakeholderVisible: true,
    },
  },
  {
    path: "capas",
    component: page("Capas"),
    meta: {
      helpTitle: "CAPAs",
      helpText: "Review corrective and preventive actions linked to investigations.",
      requiredPermission: "read",
      stakeholderVisible: true,
    },
  },
  {
    path: "charts",
    component: page("ChartView"),
    meta: {
      helpTitle: "Charts",
      helpText: "Choose a stream and date range to inspect QC results and predictive risk.",
      requiredPermission: "read",
      stakeholderVisible: true,
    },
  },
  { path: "ingest", component: page("Ingestion"), meta: { helpTitle: "Ingest QC Records", requiredPermission: "ingest_qc" } },
  { path: "imports", component: page("Imports"), meta: { helpTitle: "Import Batches", requiredPermission: "manage_imports" } },
  { path: "audit", component: page("Audit"), meta: { helpTitle: "Audit Log", requiredPermission: "read" } },
  { path: "events", component: page("Events"), meta: { helpTitle: "Events", requiredPermission: "ingest_qc" } },
  { path: "kiosks", component: page("KioskBuilder"), meta: { helpTitle: "Kiosk Builder", requiredPermission: "edit_config" } },
  { path: "config/datastreams", component: page("DatastreamSetup"), meta: { helpTitle: "Add Datastream", requiredPermission: "edit_config" } },
  { path: "config/create/:kind", component: page("ConfigCreate"), meta: { helpTitle: "Add Configuration", requiredPermission: "edit_config" } },
  { path: "config/import-profiles", component: page("ImportProfiles"), meta: { helpTitle: "Parser Profiles", requiredPermission: "manage_imports" } },
  { path: "config/instruments", component: page("Instruments"), meta: { helpTitle: "Instruments", requiredPermission: "read" } },
  { path: "config/methods", component: page("Methods"), meta: { helpTitle: "Methods", requiredPermission: "read" } },
  { path: "config/analytes", component: page("Analytes"), meta: { helpTitle: "Analytes", requiredPermission: "read" } },
  { path: "config/streams", component: page("Streams"), meta: { helpTitle: "Streams", requiredPermission: "read" } },
];
