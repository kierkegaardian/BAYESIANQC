<template>
  <el-container style="height: 100%">
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
        <el-menu-item index="/ingest">Ingest QC</el-menu-item>
        <el-menu-item index="/alerts">Alerts</el-menu-item>
        <el-menu-item index="/investigations">Investigations</el-menu-item>
        <el-menu-item index="/capas">CAPAs</el-menu-item>
        <el-menu-item index="/events">Events</el-menu-item>
        <el-menu-item index="/charts">Charts</el-menu-item>
        <el-sub-menu index="/config">
          <template #title>Configuration</template>
          <el-menu-item index="/config/instruments">Instruments</el-menu-item>
          <el-menu-item index="/config/methods">Methods</el-menu-item>
          <el-menu-item index="/config/analytes">Analytes</el-menu-item>
          <el-menu-item index="/config/streams">Streams</el-menu-item>
        </el-sub-menu>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="header">
        <div>
          <div class="header-title">{{ routeTitle }}</div>
          <div class="muted">
            API: {{ apiBase }}
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
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import { clearApiKey, getApiBase } from "../api/client";

const route = useRoute();
const router = useRouter();

const activePath = computed(() => route.path);
const routeTitle = computed(
  () => (route.meta?.helpTitle as string) || "BayesianQC"
);
const apiBase = getApiBase();

function logout() {
  clearApiKey();
  router.push("/login");
}
</script>

<style scoped>
.sidebar {
  background: #0f172a;
  color: #cbd5f5;
  padding: 16px 0;
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
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: #ffffff;
  border-bottom: 1px solid #e5e7eb;
  padding: 12px 24px;
}

.header-title {
  font-size: 18px;
  font-weight: 600;
}
</style>
