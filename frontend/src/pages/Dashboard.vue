<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2>Operational Summary</h2>
        <div class="muted">Live counts from the QC workflow.</div>
      </div>
      <el-button @click="loadSummary">Refresh</el-button>
    </div>
    <div class="card-grid">
      <el-card>
        <h3>Alerts</h3>
        <p>Total: {{ summary.alerts.total }}</p>
        <p>Open: {{ summary.alerts.open }}</p>
        <p>Acknowledged: {{ summary.alerts.acknowledged }}</p>
      </el-card>
      <el-card>
        <h3>Investigations</h3>
        <p>Total: {{ summary.investigations.total }}</p>
        <p>Open: {{ summary.investigations.open }}</p>
      </el-card>
      <el-card>
        <h3>CAPAs</h3>
        <p>Total: {{ summary.capas.total }}</p>
        <p>Open: {{ summary.capas.open }}</p>
      </el-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive } from "vue";
import { api } from "../api/client";

const summary = reactive({
  alerts: { total: 0, open: 0, acknowledged: 0 },
  investigations: { total: 0, open: 0 },
  capas: { total: 0, open: 0 },
});

async function loadSummary() {
  const data = await api.get("/reports/summary");
  summary.alerts = data.alerts;
  summary.investigations = data.investigations;
  summary.capas = data.capas;
}

onMounted(loadSummary);
</script>
