<template>
  <details class="chart-data">
    <summary>View accessible chart data ({{ records.length }} points)</summary>
    <div class="chart-data__scroll">
      <table>
        <caption class="sr-only">QC results and decision signals shown in the chart</caption>
        <thead>
          <tr><th>Time</th><th>Result</th><th>Overall status</th><th>Action risk</th><th>Signals</th><th></th></tr>
        </thead>
        <tbody>
          <tr v-for="record in displayedRecords" :key="record.id">
            <td>{{ formatTime(record.timestamp) }}</td>
            <td>{{ formatNumber(record.result_value) }}</td>
            <td>{{ formatStatus(record.disposition) }}</td>
            <td>{{ formatProbability(record.bayesian_risk) }}</td>
            <td>{{ record.signals?.map((signal) => signal.rule).join(", ") || "None" }}</td>
            <td><button type="button" @click="$emit('select', record)">Details</button></td>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-if="records.length > displayedRecords.length" class="chart-data__note">
      Showing the most recent {{ displayedRecords.length }} points.
    </p>
  </details>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type { BayesianRisk, Disposition, QCRecordChartOutEvaluated } from "../api/contracts";
import { availableRiskNumber, riskIsUnavailable } from "./bayesianRiskAvailability";

const props = defineProps<{ records: QCRecordChartOutEvaluated[] }>();
defineEmits<{ select: [record: QCRecordChartOutEvaluated] }>();
const displayedRecords = computed(() => props.records.slice(-100).reverse());

function formatTime(value: string): string {
  return new Date(value).toLocaleString();
}
function formatNumber(value: number): string {
  return Number(value).toLocaleString(undefined, { maximumFractionDigits: 3 });
}
function formatProbability(risk: BayesianRisk | null | undefined): string {
  if (riskIsUnavailable(risk)) return "Unavailable";
  const value = availableRiskNumber(risk, "probability_outside_limits");
  return value === null ? "-" : `${(value * 100).toFixed(1)}%`;
}
function formatStatus(value: Disposition | null | undefined): string {
  return value ? value.replaceAll("-", " ") : "Not evaluated";
}
</script>

<style scoped>
.chart-data { border-top: 1px solid #e2e8f0; margin-top: 8px; padding-top: 10px; }
.chart-data summary { color: #0f766e; cursor: pointer; font-weight: 600; }
.chart-data__scroll { max-height: 360px; overflow: auto; }
table { border-collapse: collapse; margin-top: 10px; min-width: 720px; width: 100%; }
th, td { border-bottom: 1px solid #e2e8f0; font-size: 12px; padding: 7px; text-align: left; }
th { background: #f8fafc; position: sticky; top: 0; }
button { background: transparent; border: 0; color: #0369a1; cursor: pointer; text-decoration: underline; }
.chart-data__note { color: #64748b; font-size: 12px; }
.sr-only { clip: rect(0 0 0 0); clip-path: inset(50%); height: 1px; overflow: hidden; position: absolute; width: 1px; }
</style>
