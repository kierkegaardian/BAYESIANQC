import { createRouter, createWebHistory } from "vue-router";

import AppLayout from "../components/AppLayout.vue";
import Dashboard from "../pages/Dashboard.vue";
import Login from "../pages/Login.vue";
import Instruments from "../pages/Instruments.vue";
import Methods from "../pages/Methods.vue";
import Analytes from "../pages/Analytes.vue";
import Streams from "../pages/Streams.vue";
import Ingestion from "../pages/Ingestion.vue";
import Alerts from "../pages/Alerts.vue";
import Investigations from "../pages/Investigations.vue";
import Capas from "../pages/Capas.vue";
import Events from "../pages/Events.vue";
import ChartView from "../pages/ChartView.vue";
import { getApiKey } from "../api/client";

const routes = [
  {
    path: "/login",
    component: Login,
    meta: {
      helpTitle: "Login",
      helpText:
        "Enter a valid API key and click Connect. The default local key is local-dev-key.",
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
        path: "ingest",
        component: Ingestion,
        meta: {
          helpTitle: "Ingest QC Records",
          helpText:
            "Select a stream, enter a result, and click Submit. Use CSV upload for batch ingestion.",
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
        path: "charts",
        component: ChartView,
        meta: {
          helpTitle: "Charts",
          helpText:
            "Choose a stream and date range, then click Load to render QC trends and alerts.",
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
