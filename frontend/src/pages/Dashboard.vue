<template>
  <div class="page dashboard-page">
    <div class="page-header">
      <div>
        <h2>{{ stakeholder ? "Stakeholder Demo" : "Operational Summary" }}</h2>
        <div class="muted">{{ stakeholder ? "Explore a synthetic, multi-domain QC workflow." : "Live counts from the QC workflow." }}</div>
      </div>
      <el-button :loading="loading" @click="loadSummary">Refresh</el-button>
    </div>

    <el-alert v-if="error" type="error" :closable="false" show-icon class="section-card">
      <template #title>Summary data could not be loaded.</template>
      <el-button size="small" @click="loadSummary">Retry</el-button>
    </el-alert>
    <el-skeleton v-if="loading && !hasLoaded" :rows="5" animated />

    <template v-else-if="hasLoaded">
      <section v-if="stakeholder" class="demo-intro section-card" aria-labelledby="demo-intro-title">
        <div>
          <el-tag type="warning">Synthetic stakeholder demonstration — not validated for laboratory use</el-tag>
          <h3 id="demo-intro-title">See traditional QC signals and predictive risk together</h3>
          <p>Start with the multi-chart overview, then inspect one stream and follow its workflow into alerts and investigation.</p>
        </div>
        <router-link to="/kiosk/demo" class="primary-link">Open demo overview</router-link>
      </section>

      <div class="card-grid summary-grid" aria-label="Active workflow summary">
        <router-link to="/alerts?status=open" class="summary-link">
          <el-card shadow="hover"><div class="metric">{{ summary.alerts.open }}</div><h3>Open alerts</h3><p>{{ summary.alerts.acknowledged }} acknowledged · {{ summary.alerts.total }} total</p></el-card>
        </router-link>
        <router-link to="/investigations" class="summary-link">
          <el-card shadow="hover"><div class="metric">{{ summary.investigations.open }}</div><h3>Open investigations</h3><p>{{ summary.investigations.total }} total investigations</p></el-card>
        </router-link>
        <router-link to="/capas" class="summary-link">
          <el-card shadow="hover"><div class="metric">{{ summary.capas.open }}</div><h3>Open CAPAs</h3><p>{{ summary.capas.total }} total actions</p></el-card>
        </router-link>
      </div>

      <section v-if="stakeholder" class="scenario-section">
        <h3>Choose a demonstration domain</h3>
        <div class="scenario-grid">
          <router-link v-for="scenario in scenarios" :key="scenario.path" :to="scenario.path" class="scenario-card">
            <strong>{{ scenario.title }}</strong><span>{{ scenario.description }}</span>
          </router-link>
        </div>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { api } from "../api/client";
import type { ReportSummaryOut } from "../api/contracts";
import { isStakeholderDeployment } from "../deployment";

const stakeholder = isStakeholderDeployment;
const loading = ref(false);
const hasLoaded = ref(false);
const error = ref(false);
const summary = reactive<ReportSummaryOut>({
  alerts: { total: 0, open: 0, acknowledged: 0, closed: 0 },
  investigations: { total: 0, open: 0 },
  capas: { total: 0, open: 0 },
});
const scenarios = [
  { path: "/kiosk/fuel", title: "Fuel testing", description: "Distillation, flash point, sulfur, and color QC." },
  { path: "/kiosk/medical", title: "Clinical laboratory", description: "Stable controls, drift, shifts, and review signals." },
  { path: "/kiosk/pharma", title: "Pharmaceutical QC", description: "Assay, impurity, dissolution, and stability examples." },
  { path: "/kiosk/steel", title: "Steel and metals", description: "Composition, coating, furnace, and precision examples." },
];

async function loadSummary(): Promise<void> {
  loading.value = true;
  error.value = false;
  try {
    const data = await api.get<ReportSummaryOut>("/reports/summary");
    Object.assign(summary.alerts, data.alerts);
    Object.assign(summary.investigations, data.investigations);
    Object.assign(summary.capas, data.capas);
    hasLoaded.value = true;
  } catch {
    hasLoaded.value = false;
    error.value = true;
  } finally {
    loading.value = false;
  }
}

onMounted(() => { void loadSummary(); });
</script>

<style scoped>
.dashboard-page { max-width: 1240px; }
.demo-intro { align-items: center; background: linear-gradient(135deg, #0f172a, #1e3a5f); border-radius: 12px; color: #f8fafc; display: flex; gap: 28px; justify-content: space-between; padding: 24px; }
.demo-intro h3 { font-size: 22px; margin: 12px 0 6px; }
.demo-intro p { color: #dbeafe; margin: 0; max-width: 720px; }
.demo-intro :deep(.el-tag) { height: auto; max-width: 100%; white-space: normal; }
.primary-link { background: #f59e0b; border-radius: 7px; color: #111827; flex-shrink: 0; font-weight: 700; padding: 11px 16px; text-decoration: none; }
.summary-link { color: inherit; min-width: 0; text-decoration: none; }
.summary-link :deep(.el-card) { height: 100%; }
.summary-link h3 { margin: 5px 0; }
.summary-link p { color: #64748b; margin: 0; }
.metric { color: #0f766e; font-size: 32px; font-weight: 750; }
.scenario-section { margin-top: 28px; }
.scenario-grid { display: grid; gap: 12px; grid-template-columns: repeat(4, minmax(0, 1fr)); }
.scenario-card { background: #fff; border: 1px solid #dbe3ee; border-radius: 9px; color: #0f172a; display: grid; gap: 6px; padding: 16px; text-decoration: none; }
.scenario-card:hover, .scenario-card:focus-visible { border-color: #0d9488; box-shadow: 0 4px 14px rgba(15, 23, 42, 0.08); outline: none; }
.scenario-card span { color: #64748b; font-size: 13px; }
@media (max-width: 900px) { .scenario-grid { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 600px) { .demo-intro { align-items: flex-start; flex-direction: column; } .scenario-grid { grid-template-columns: 1fr; } }
</style>
