<template>
  <el-container class="app-shell">
    <el-aside width="240px" class="sidebar">
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
        <el-menu-item index="/ingest">Ingest QC</el-menu-item>
        <el-menu-item index="/quarantine">Quarantine</el-menu-item>
        <el-menu-item index="/imports">Imports</el-menu-item>
        <el-menu-item index="/alerts">Alerts</el-menu-item>
        <el-menu-item index="/audit">Audit</el-menu-item>
        <el-menu-item index="/investigations">Investigations</el-menu-item>
        <el-menu-item index="/capas">CAPAs</el-menu-item>
        <el-menu-item index="/events">Events</el-menu-item>
        <el-menu-item index="/charts">Charts</el-menu-item>
        <el-sub-menu index="/kiosk">
          <template #title>Kiosks</template>
          <el-menu-item index="/kiosks">Kiosk Builder</el-menu-item>
          <el-menu-item index="/kiosk/demo">Demo Suite</el-menu-item>
          <el-menu-item index="/kiosk/fuel">Fuel ASTM</el-menu-item>
          <el-menu-item index="/kiosk/medical">Medical</el-menu-item>
          <el-menu-item index="/kiosk/pharma">Pharma QC</el-menu-item>
          <el-menu-item index="/kiosk/steel">Steel / Metals</el-menu-item>
          <el-menu-item index="/kiosk/refinery">Refinery</el-menu-item>
          <el-menu-item index="/kiosk/charts">Base Charts</el-menu-item>
        </el-sub-menu>
        <el-sub-menu index="/config">
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
        <div>
          <div class="header-title">{{ routeTitle }}</div>
          <div class="muted">
            API: {{ apiBase }}
          </div>
          <div v-if="sessionUser" class="muted">
            Role: {{ sessionUser.role }} · Key #{{ sessionUser.api_key_id ?? "unknown" }}
          </div>
        </div>
        <div class="header-actions">
          <el-button type="primary" plain @click="logout">Log out</el-button>
        </div>
      </el-header>
      <el-main>
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { computed, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { clearApiKey, getApiBase } from "../api/client";
import { clearSessionUser, loadSessionUser, sessionUser } from "../api/session";

const route = useRoute();
const router = useRouter();

const activePath = computed(() => route.path);
const routeTitle = computed(
  () => route.meta.helpTitle ?? "BayesianQC"
);
const apiBase = getApiBase();

function logout() {
  clearApiKey();
  clearSessionUser();
  router.push("/login");
}

onMounted(() => {
  void loadSessionUser().catch(() => {
    clearApiKey();
    clearSessionUser();
    router.push("/login");
  });
});
</script>

<style scoped>
.sidebar {
  background: #0f172a;
  color: #cbd5f5;
  flex-shrink: 0;
  padding: 16px 0;
}

.app-shell {
  height: 100%;
  min-width: 0;
}

.content-shell {
  min-width: 0;
}

.brand {
  padding: 0 20px 20px 20px;
}

.brand-title {
  font-weight: 700;
  font-size: 18px;
  color: #f8fafc;
}

.brand-subtitle {
  font-size: 12px;
  color: #94a3b8;
}

.menu {
  border-right: none;
}

.header {
  align-items: center;
  background: #ffffff;
  border-bottom: 1px solid #e5e7eb;
  display: flex;
  gap: 16px;
  height: auto;
  justify-content: space-between;
  min-height: 84px;
  padding: 12px 24px;
}

.header-title {
  font-size: 18px;
  font-weight: 600;
}

.header > div:first-child {
  min-width: 0;
}

.header-actions {
  flex-shrink: 0;
}

.el-main {
  min-width: 0;
  overflow: auto;
}

@media (max-width: 760px) {
  .app-shell {
    flex-direction: column;
    height: auto;
    min-height: 100%;
  }

  .sidebar {
    padding: 12px 0;
    width: 100% !important;
  }

  .brand {
    padding: 0 16px 12px;
  }

  .header {
    align-items: stretch;
    padding: 12px 16px;
  }

  .header-actions {
    align-self: flex-start;
  }

  .el-main {
    padding: 12px;
  }
}
</style>
