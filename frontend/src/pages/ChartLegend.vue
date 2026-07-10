<template>
  <div class="chart-legend" aria-label="Chart legend">
    <span v-for="item in items" :key="item.label" class="chart-legend__item">
      <i :style="{ background: item.color }" aria-hidden="true"></i>{{ item.label }}
    </span>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{ mode: "results" | "risk" | "both" }>();
const resultItems = [
  { label: "QC result", color: "#2563eb" },
  { label: "Configured mean", color: "#0f172a" },
  { label: "Warning limits", color: "#f59e0b" },
  { label: "Action limits", color: "#ef4444" },
  { label: "Posterior mean", color: "#16a34a" },
  { label: "Predictive interval", color: "#14b8a6" },
  { label: "Mean credible interval", color: "#64748b" },
  { label: "Lot / event marker", color: "#0ea5e9" },
  { label: "Alert", color: "#7f1d1d" },
];
const riskItems = [
  { label: "Warning probability", color: "#f59e0b" },
  { label: "Action probability", color: "#dc2626" },
  { label: "Risk threshold", color: "#991b1b" },
  { label: "Event marker", color: "#0ea5e9" },
  { label: "Alert", color: "#7f1d1d" },
];
const items = computed(() => props.mode === "results" ? resultItems : props.mode === "risk" ? riskItems : [...resultItems, ...riskItems.slice(0, 4)]);
</script>

<style scoped>
.chart-legend { display: flex; flex-wrap: wrap; gap: 8px 16px; padding: 4px 0; }
.chart-legend__item { align-items: center; color: #475569; display: inline-flex; font-size: 12px; gap: 6px; }
.chart-legend i { border-radius: 999px; height: 4px; width: 18px; }
</style>
