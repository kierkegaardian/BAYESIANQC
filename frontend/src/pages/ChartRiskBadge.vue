<template>
  <div
    class="risk-badge"
    :class="[`risk-badge--${tone}`, { 'risk-badge--kiosk': kiosk }]"
    :title="tooltip"
    aria-live="polite"
  >
    <span class="risk-badge__eyebrow">Bayesian</span>
    <strong>{{ summary?.riskLabel ?? "Risk -" }}</strong>
    <span>{{ summary?.stateLabel ?? "No data" }}</span>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { bayesianRiskHelpText } from "./chartRisk";
import type { ChartRiskSummary } from "./chartRisk";

const props = withDefaults(
  defineProps<{
    summary: ChartRiskSummary | null;
    kiosk?: boolean;
  }>(),
  {
    kiosk: false,
  }
);

const tone = computed(() => props.summary?.tone ?? "none");
const tooltip = computed(() => {
  if (!props.summary) {
    return "No Bayesian risk is available for the current stream.";
  }
  return bayesianRiskHelpText("at the highlighted condition in the current chart window");
});
</script>

<style scoped>
.risk-badge {
  align-items: center;
  border: 1px solid #cbd5e1;
  border-left-width: 5px;
  border-radius: 8px;
  display: grid;
  gap: 2px;
  min-width: 128px;
  padding: 8px 12px;
}

.risk-badge__eyebrow,
.risk-badge span {
  color: #64748b;
  font-size: 12px;
  line-height: 1.2;
}

.risk-badge strong {
  color: #0f172a;
  font-size: 18px;
  line-height: 1.1;
}

.risk-badge--low {
  background: #f0fdf4;
  border-color: #86efac;
}

.risk-badge--monitor {
  background: #fffbeb;
  border-color: #f59e0b;
}

.risk-badge--hold,
.risk-badge--action {
  background: #fef2f2;
  border-color: #ef4444;
}

.risk-badge--none {
  background: #f8fafc;
}

.risk-badge--kiosk {
  background: #0f172a;
  border-color: #475569;
  min-width: 168px;
}

.risk-badge--kiosk.risk-badge--low {
  border-color: #22c55e;
}

.risk-badge--kiosk.risk-badge--monitor {
  border-color: #f59e0b;
}

.risk-badge--kiosk.risk-badge--hold,
.risk-badge--kiosk.risk-badge--action {
  border-color: #ef4444;
}

.risk-badge--kiosk strong {
  color: #f8fafc;
}

.risk-badge--kiosk .risk-badge__eyebrow,
.risk-badge--kiosk span {
  color: #cbd5e1;
}
</style>
