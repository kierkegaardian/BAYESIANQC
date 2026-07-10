<template>
  <el-container class="app-shell">
    <button v-if="navOpen" class="nav-backdrop" aria-label="Close navigation" @click="navOpen = false" />
    <el-aside width="240px" class="sidebar" :class="{ 'sidebar--open': navOpen }">
      <div class="brand">
        <div class="brand-title">BayesianQC</div>
        <div class="brand-subtitle">Quality Control Console</div>
      </div>
      <el-menu
        :default-active="activePath"
        class="menu"
        router
        background-color="#0f172a"
        text-color="#cbd5f5"
        active-text-color="#f59e0b"
      >
        <el-menu-item index="/">Dashboard</el-menu-item>
        <el-menu-item index="/backlog">QC Backlog</el-menu-item>
        <el-menu-item v-if="!stakeholder" index="/ingest">Ingest QC</el-menu-item>
        <el-menu-item index="/quarantine">Quarantine</el-menu-item>
        <el-menu-item v-if="!stakeholder" index="/imports">Imports</el-menu-item>
        <el-menu-item index="/alerts">Alerts</el-menu-item>
        <el-menu-item v-if="!stakeholder" index="/audit">Audit</el-menu-item>
        <el-menu-item index="/investigations">Investigations</el-menu-item>
        <el-menu-item index="/capas">CAPAs</el-menu-item>
        <el-menu-item v-if="!stakeholder" index="/events">Events</el-menu-item>
        <el-menu-item index="/charts">Charts</el-menu-item>
        <el-sub-menu index="/kiosk">
          <template #title>Kiosks</template>
          <el-menu-item v-if="!stakeholder" index="/kiosks">Kiosk Builder</el-menu-item>
          <el-menu-item index="/kiosk/demo">Demo Overview</el-menu-item>
          <el-menu-item index="/kiosk/fuel">Fuel</el-menu-item>
          <el-menu-item index="/kiosk/medical">Medical</el-menu-item>
          <el-menu-item index="/kiosk/pharma">Pharma</el-menu-item>
          <el-menu-item index="/kiosk/steel">Steel / Metals</el-menu-item>
          <el-menu-item v-if="!stakeholder" index="/kiosk/refinery">Refinery</el-menu-item>
          <el-menu-item v-if="!stakeholder" index="/kiosk/charts">Base Charts</el-menu-item>
        </el-sub-menu>
        <el-sub-menu v-if="!stakeholder" index="/config">
          <template #title>Configuration</template>
          <el-menu-item index="/config/datastreams">Add Datastream</el-menu-item>
          <el-menu-item index="/config/import-profiles">Parser Profiles</el-menu-item>
          <el-menu-item index="/config/instruments">Instruments</el-menu-item>
          <el-menu-item index="/config/methods">Methods</el-menu-item>
          <el-menu-item index="/config/analytes">Analytes</el-menu-item>
          <el-menu-item index="/config/streams">Streams</el-menu-item>
        </el-sub-menu>
      </el-menu>
    </el-aside>
    <el-container class="content-shell">
      <el-header class="header">
        <div class="header-leading">
          <el-button class="menu-toggle" aria-label="Open navigation" text @click="navOpen = true">☰</el-button>
          <div>
            <div class="header-title">{{ routeTitle }}</div>
            <template v-if="!stakeholder">
              <div class="muted">API: {{ apiBase }}</div>
              <div v-if="sessionUser" class="muted">Role: {{ sessionUser.role }} · Key #{{ sessionUser.api_key_id ?? "unknown" }}</div>
            </template>
            <div v-else-if="sessionUser" class="muted">Guided stakeholder workflow access</div>
          </div>
        </div>
        <div v-if="!edgeAuth" class="header-actions">
          <el-button type="primary" plain @click="logout">Log out</el-button>
        </div>
      </el-header>
      <StakeholderBanner v-if="stakeholder" />
      <el-alert
        v-if="connectionError"
        class="connection-alert"
        type="error"
        :closable="false"
        title="The application API is unavailable. Displayed information may be out of date."
        show-icon
      >
        <el-button size="small" @click="loadCurrentUser">Retry</el-button>
      </el-alert>
      <el-main><router-view /></el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ApiError, clearApiKey, getApiBase, usesEdgeAuth } from "../api/client";
import { clearSessionUser, loadSessionUser, sessionUser } from "../api/session";
import { isStakeholderDeployment } from "../deployment";
import StakeholderBanner from "./StakeholderBanner.vue";

const route = useRoute();
const router = useRouter();
const navOpen = ref(false);
const connectionError = ref(false);
const stakeholder = isStakeholderDeployment;
const apiBase = getApiBase();
const edgeAuth = usesEdgeAuth();
const activePath = computed(() => route.path);
const routeTitle = computed(() => route.meta.helpTitle ?? "BayesianQC");

function logout(): void {
  clearApiKey();
  clearSessionUser();
  void router.push("/login");
}

async function loadCurrentUser(): Promise<void> {
  try {
    await loadSessionUser();
    connectionError.value = false;
  } catch (error) {
    if (!edgeAuth && error instanceof ApiError && error.status === 401) {
      logout();
      return;
    }
    connectionError.value = true;
  }
}

watch(() => route.fullPath, () => { navOpen.value = false; });
onMounted(() => { void loadCurrentUser(); });
</script>

<style scoped>
.app-shell { height: 100%; min-width: 0; }
.sidebar { background: #0f172a; color: #cbd5f5; flex-shrink: 0; padding: 16px 0; z-index: 2100; }
.brand { padding: 0 20px 20px; }
.brand-title { color: #f8fafc; font-size: 18px; font-weight: 700; }
.brand-subtitle { color: #94a3b8; font-size: 12px; }
.menu { border-right: none; }
.content-shell { min-width: 0; }
.header { align-items: center; background: #fff; border-bottom: 1px solid #e5e7eb; display: flex; gap: 16px; height: auto; justify-content: space-between; min-height: 84px; padding: 12px 24px; }
.header-leading { align-items: center; display: flex; gap: 10px; min-width: 0; }
.header-title { font-size: 18px; font-weight: 600; }
.header-actions { flex-shrink: 0; }
.menu-toggle { display: none; font-size: 22px; padding: 6px; }
.connection-alert { border-radius: 0; }
.connection-alert :deep(.el-alert__content) { align-items: center; display: flex; gap: 12px; }
.el-main { min-width: 0; overflow: auto; }
.nav-backdrop { display: none; }

@media (max-width: 760px) {
  .app-shell { height: 100%; }
  .sidebar { bottom: 0; left: 0; overflow: auto; position: fixed; top: 0; transform: translateX(-100%); transition: transform 160ms ease; width: min(280px, 84vw) !important; }
  .sidebar--open { transform: translateX(0); }
  .nav-backdrop { background: rgba(15, 23, 42, 0.5); border: 0; bottom: 0; display: block; left: 0; position: fixed; right: 0; top: 0; z-index: 2050; }
  .menu-toggle { display: inline-flex; }
  .header { min-height: 72px; padding: 10px 12px; }
  .header-leading { align-items: flex-start; }
  .el-main { padding: 12px; }
}
</style>
