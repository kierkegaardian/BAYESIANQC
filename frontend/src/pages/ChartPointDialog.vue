<template>
  <el-dialog
    :model-value="modelValue"
    :title="kiosk ? 'QC Point Detail' : 'QC Point Comments'"
    :width="dialogWidth"
    destroy-on-close
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <div v-if="point" class="point-context">
      <div><span>Record</span><strong>#{{ point.record_id }}</strong></div>
      <div><span>Time</span><strong>{{ formatPointTime(point.value[0]) }}</strong></div>
      <div><span>Result</span><strong>{{ point.value[1] ?? "outlier" }}</strong></div>
      <div><span>Overall status</span><strong>{{ point.disposition ?? "-" }}</strong></div>
      <div><span>Frequentist signals</span><strong>{{ signalLabel }}</strong></div>
      <div><span>{{ riskHeading }}</span><strong>{{ riskLabel }}</strong></div>
    </div>
    <QCCommentThread
      v-if="point"
      target-type="qc_record"
      :target-id="String(point.record_id)"
      title="Record Comments"
    />
    <template #footer>
      <el-button @click="close">Close</el-button>
      <el-button
        v-if="canResolveQc && point?.include_in_stats === false"
        type="primary"
        @click="promptResolution(true)"
      >Reinstate</el-button>
      <el-button
        v-if="canResolveQc && point?.include_in_stats !== false"
        type="warning"
        @click="promptResolution(false)"
      >Exclude From Stats</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { api } from "../api/client";
import type { QCRecordResolutionIn } from "../api/contracts";
import { canResolveQc } from "../api/session";
import QCCommentThread from "../components/QCCommentThread.vue";
import { formatPointTime, type ChartPoint } from "./chartPoint";
import { availableRiskNumber, riskIsUnavailable, unavailableRiskReason } from "./bayesianRiskAvailability";

const props = defineProps<{ modelValue: boolean; point: ChartPoint | null; kiosk: boolean }>();
const emit = defineEmits<{ "update:modelValue": [value: boolean]; resolved: [] }>();

const dialogWidth = computed(() => props.kiosk ? "min(760px, calc(100vw - 32px))" : "min(560px, calc(100vw - 32px))");
const signalLabel = computed(() => props.point?.signals?.map((signal) => signal.rule).join(", ") || "none");
const riskHeading = computed(() => riskIsUnavailable(props.point?.bayesian_risk) ? "Bayesian inference" : "Bayesian risk score");
const riskLabel = computed(() => {
  const risk = props.point?.bayesian_risk;
  if (riskIsUnavailable(risk)) return `Unavailable — ${unavailableRiskReason(risk)}`;
  const score = availableRiskNumber(risk, "risk_score");
  return score === null ? "-" : `${score.toFixed(0)}/100`;
});

function close(): void {
  emit("update:modelValue", false);
}

async function updateResolution(includeInStats: boolean, reason: string): Promise<boolean> {
  if (!props.point) return false;
  const payload: QCRecordResolutionIn = {
    include_in_stats: includeInStats,
    resolved_reason: reason || null,
  };
  try {
    await api.patch(`/qc/records/${props.point.record_id}/resolution`, payload);
    ElMessage.success(includeInStats ? "Record reinstated" : "Record resolved");
    emit("resolved");
    return true;
  } catch (error) {
    ElMessage.error(error instanceof Error && error.message ? error.message : "Failed to update record");
    return false;
  }
}

async function promptResolution(includeInStats: boolean): Promise<void> {
  if (!props.point || !canResolveQc.value) return;
  const result = await ElMessageBox.prompt(
    includeInStats ? "Reason" : "Why should this point be excluded from stats?",
    includeInStats ? "Reinstate QC Point" : "Resolve QC Point",
    {
      confirmButtonText: includeInStats ? "Reinstate" : "Resolve",
      cancelButtonText: "Cancel",
      inputPlaceholder: includeInStats
        ? "Why should this point be included again?"
        : "e.g. reagent lot change or known variation",
    }
  ).catch(() => null);
  if (result && await updateResolution(includeInStats, result.value)) close();
}
</script>

<style scoped>
.point-context { display: grid; gap: 8px; grid-template-columns: repeat(2, minmax(0, 1fr)); margin-bottom: 16px; }
.point-context div { background: #f8fafc; border: 1px solid #e5e7eb; border-radius: 6px; min-width: 0; overflow-wrap: anywhere; padding: 8px; }
.point-context span { color: #64748b; display: block; font-size: 12px; }
.point-context strong { display: block; margin-top: 2px; }
@media (max-width: 760px) { .point-context { grid-template-columns: 1fr; } }
</style>
