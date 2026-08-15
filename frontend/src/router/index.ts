import { createRouter, createWebHistory } from "vue-router";

import AppLayout from "../components/AppLayout.vue";
import Dashboard from "../pages/Dashboard.vue";
import Login from "../pages/Login.vue";
import Instruments from "../pages/Instruments.vue";
import Methods from "../pages/Methods.vue";
import Analytes from "../pages/Analytes.vue";
import Streams from "../pages/Streams.vue";
import Ingestion from "../pages/Ingestion.vue";
import Backlog from "../pages/Backlog.vue";
import Quarantine from "../pages/Quarantine.vue";
import Imports from "../pages/Imports.vue";
import Alerts from "../pages/Alerts.vue";
import Audit from "../pages/Audit.vue";
import Investigations from "../pages/Investigations.vue";
import Capas from "../pages/Capas.vue";
import Events from "../pages/Events.vue";
import ChartView from "../pages/ChartView.vue";
import ChartKiosk from "../pages/ChartKiosk.vue";
import KioskBuilder from "../pages/KioskBuilder.vue";
import DatastreamSetup from "../pages/DatastreamSetup.vue";
import ConfigCreate from "../pages/ConfigCreate.vue";
import ImportProfiles from "../pages/ImportProfiles.vue";
import { getApiKey, usesEdgeAuth } from "../api/client";

const routes = [
  {
    path: "/login",
    component: Login,
    meta: {
      helpTitle: "Login",
      helpText:
        "Enter a valid API key and click Connect. Local demos may seed local-dev-key.",
    },
  },
  {
    path: "/kiosk/charts",
    component: ChartKiosk,
    meta: {
      hideHelp: true,
      helpTitle: "Chart Kiosk",
      helpText: "Rotates the seeded HbA1c and D86 chart streams.",
    },
  },
  {
    path: "/kiosk/refinery",
    component: ChartKiosk,
    meta: {
      hideHelp: true,
      helpTitle: "Refinery Kiosk",
      helpText: "Rotates the seeded refinery D86, color, pour point, and sulfur streams.",
    },
  },
  {
    path: "/kiosk/demo",
    component: ChartKiosk,
    meta: {
      hideHelp: true,
      helpTitle: "Demo Kiosk",
      helpText: "Rotates representative synthetic fuel, medical, pharma, and steel QC streams.",
    },
  },
  {
    path: "/kiosk/fuel",
    component: ChartKiosk,
    meta: {
      hideHelp: true,
      helpTitle: "Fuel ASTM Kiosk",
      helpText: "Rotates synthetic fuel and ASTM-style QC demo streams.",
    },
  },
  {
    path: "/kiosk/medical",
    component: ChartKiosk,
    meta: {
      hideHelp: true,
      helpTitle: "Medical Kiosk",
      helpText: "Rotates synthetic clinical laboratory QC demo streams.",
    },
  },
  {
    path: "/kiosk/pharma",
    component: ChartKiosk,
    meta: {
      hideHelp: true,
      helpTitle: "Pharma QC Kiosk",
      helpText: "Rotates synthetic pharmaceutical QC demo streams.",
    },
  },
  {
    path: "/kiosk/steel",
    component: ChartKiosk,
    meta: {
      hideHelp: true,
      helpTitle: "Steel Kiosk",
      helpText: "Rotates synthetic steel and metals QC demo streams.",
    },
  },
  {
    path: "/kiosk/:slug",
    component: ChartKiosk,
    meta: {
      hideHelp: true,
      helpTitle: "Saved Kiosk",
      helpText: "Displays a saved kiosk layout configured from datastream setup.",
    },
  },
  {
    path: "/",
    component: AppLayout,
    children: [
      {
        path: "",
        component: Dashboard,
        meta: {
          helpTitle: "Dashboard",
          helpText:
            "Review alert/investigation/CAPA counts and click Refresh to reload the data.",
        },
      },
      {
        path: "config/datastreams",
        component: DatastreamSetup,
        meta: {
          helpTitle: "Add Datastream",
          helpText:
            "Create or reuse instrument, method, parameter, material, stream, prior, and optional kiosk assignment.",
        },
      },
      {
        path: "config/create/:kind",
        component: ConfigCreate,
        meta: {
          helpTitle: "Add Configuration",
          helpText: "Create a governed configuration record and return to datastream setup.",
        },
      },
      {
        path: "config/import-profiles",
        component: ImportProfiles,
        meta: {
          helpTitle: "Parser Profiles",
          helpText:
            "Create active or draft parser profiles that map instrument files into import previews.",
        },
      },
      {
        path: "config/instruments",
        component: Instruments,
        meta: {
          helpTitle: "Instruments",
          helpText:
            "Click Add Instrument to create one, or Edit to update existing instrument details.",
        },
      },
      {
        path: "config/methods",
        component: Methods,
        meta: {
          helpTitle: "Methods",
          helpText:
            "Select an instrument, enter a method name, and click Save to add or edit methods.",
        },
      },
      {
        path: "config/analytes",
        component: Analytes,
        meta: {
          helpTitle: "Analytes",
          helpText:
            "Pick a method, enter analyte details, and click Save to manage analytes and default units.",
        },
      },
      {
        path: "config/streams",
        component: Streams,
        meta: {
          helpTitle: "Streams",
          helpText:
            "Fill the stream form and click Save. Use Versions to view historical configurations.",
        },
      },
      {
        path: "backlog",
        component: Backlog,
        meta: {
          helpTitle: "QC Backlog",
          helpText:
            "Review scheduled or requested QC work by instrument, bench, group, or assignee.",
        },
      },
      {
        path: "ingest",
        component: Ingestion,
        meta: {
          helpTitle: "Ingest QC Records",
          helpText:
            "Select a stream, enter a result, and click Submit. Use CSV upload for batch ingestion.",
        },
      },
      {
        path: "quarantine",
        component: Quarantine,
        meta: {
          helpTitle: "Quarantine",
          helpText:
            "Review rows preserved before ingestion and record a reviewed or rejected decision.",
        },
      },
      {
        path: "imports",
        component: Imports,
        meta: {
          helpTitle: "Import Batches",
          helpText:
            "Upload instrument files, review parsed rows, associate runs, inspect artifacts, and apply ready QC rows.",
        },
      },
      {
        path: "alerts",
        component: Alerts,
        meta: {
          helpTitle: "Alerts",
          helpText:
            "Review alerts, update status or assignment, then click Save on the row.",
        },
      },
      {
        path: "audit",
        component: Audit,
        meta: {
          helpTitle: "Audit Log",
          helpText:
            "Filter audit entries, expand rows to compare before and after snapshots, or export the current result set.",
        },
      },
      {
        path: "investigations",
        component: Investigations,
        meta: {
          helpTitle: "Investigations",
          helpText:
            "Create a new investigation or edit an existing one to track findings and decisions.",
        },
      },
      {
        path: "capas",
        component: Capas,
        meta: {
          helpTitle: "CAPAs",
          helpText:
            "Create or edit CAPAs by filling required actions, owners, and due dates, then click Save.",
        },
      },
      {
        path: "events",
        component: Events,
        meta: {
          helpTitle: "Events",
          helpText:
            "Add calibration/maintenance/lot-change events to annotate QC timelines.",
        },
      },
      {
        path: "kiosks",
        component: KioskBuilder,
        meta: {
          helpTitle: "Kiosk Builder",
          helpText:
            "Create saved kiosk layouts, add stream panels, and open the fullscreen kiosk display.",
        },
      },
      {
        path: "charts",
        component: ChartView,
        meta: {
          helpTitle: "Charts",
          helpText:
            "Choose a stream and date range, then click Load to render QC trends, alerts, and control-material lot segments.",
        },
      },
    ],
  },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

router.beforeEach((to) => {
  if (usesEdgeAuth()) {
    return to.path === "/login" ? "/" : true;
  }
  if (to.path === "/login") {
    return true;
  }
  const apiKey = getApiKey();
  if (!apiKey) {
    return "/login";
  }
  return true;
});

export default router;
