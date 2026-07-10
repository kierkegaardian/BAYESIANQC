import { createRouter, createWebHistory } from "vue-router";

import { ApiError, getApiKey, usesEdgeAuth } from "../api/client";
import { isStakeholderDeployment } from "../deployment";
import { hasPermission, loadSessionUser, sessionUser } from "../api/session";
import { appChildren } from "./appRoutes";
import { kioskRoutes } from "./kioskRoutes";
import { stakeholderRedirect } from "./accessPolicy";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/login",
      component: () => import("../pages/Login.vue"),
      meta: { helpTitle: "Login", helpText: "Enter a valid API key and connect." },
    },
    ...kioskRoutes,
    {
      path: "/",
      component: () => import("../components/AppLayout.vue"),
      children: appChildren,
    },
    { path: "/:pathMatch(.*)*", redirect: "/" },
  ],
});

router.beforeEach(async (to) => {
  const stakeholderRoute = stakeholderRedirect({
    stakeholderDeployment: isStakeholderDeployment,
    path: to.path,
    stakeholderVisible: to.meta.stakeholderVisible === true,
  });
  if (stakeholderRoute) return stakeholderRoute;
  if (usesEdgeAuth()) {
    if (to.path === "/login") return "/";
  } else {
    if (to.path === "/login") return true;
    if (!getApiKey()) {
      return { path: "/login", query: { redirect: to.fullPath } };
    }
  }
  if (to.meta.requiredPermission) {
    try {
      if (!sessionUser.value) await loadSessionUser();
      if (!hasPermission(to.meta.requiredPermission)) return "/";
    } catch (error) {
      if (!usesEdgeAuth() && error instanceof ApiError && error.status === 401) {
        return { path: "/login", query: { redirect: to.fullPath } };
      }
      // AppLayout presents connection errors without turning them into false authorization decisions.
    }
  }
  return true;
});

export default router;
