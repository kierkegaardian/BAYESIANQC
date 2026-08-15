<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2>Alerts</h2>
        <div class="muted">Review and update alert status.</div>
      </div>
      <el-button @click="loadAlerts">Refresh</el-button>
    </div>

    <el-table :data="alerts" stripe class="full-width">
      <el-table-column type="expand">
        <template #default="{ row }">
          <div class="alert-evaluation-detail">
            <div><span>Evaluation status</span><strong>{{ row.evaluation_status }}</strong></div>
            <div><span>Source evaluation</span><strong>{{ row.source_evaluation_id ?? "legacy unavailable" }}</strong></div>
            <div><span>Current evaluation</span><strong>{{ row.current_evaluation_id ?? "legacy unavailable" }}</strong></div>
            <div><span>Replacement alert</span><strong>{{ row.replacement_alert_id ?? "none" }}</strong></div>
            <div><span>Threshold mode</span><strong>{{ row.evaluation?.threshold_mode ?? "legacy unavailable" }}</strong></div>
            <div><span>Risk semantics</span><strong>{{ row.evaluation?.risk_semantics ?? "legacy unavailable" }}</strong></div>
          </div>
          <el-alert
            v-if="row.evaluation_status === 'legacy_unverified'"
            type="warning"
            :closable="false"
            title="Evaluation provenance unavailable; historical limits are not inferred."
            style="margin-bottom: 12px"
          />
          <div class="comment-panel">
            <QCCommentThread target-type="alert" :target-id="row.id" title="Alert Comments" />
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="id" label="Alert ID" />
      <el-table-column prop="stream_id" label="Stream" />
      <el-table-column prop="qc_record_timestamp" label="QC Time" width="180" />
      <el-table-column prop="created_at" label="Created" width="180" />
      <el-table-column prop="disposition" label="Disposition" />
      <el-table-column label="Next-result risk" width="130">
        <template #default="{ row }">
          <span>{{ row.bayesian_risk?.risk_score ?? "-" }}</span>
        </template>
      </el-table-column>
      <el-table-column label="Signals">
        <template #default="{ row }">
          <span>
            {{ formatSignalRules(row) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column prop="status" label="Status" />
      <el-table-column v-if="canApprove" label="Assign">
        <template #default="{ row }">
          <el-input v-model="row.assigned_to" placeholder="Assignee" />
        </template>
      </el-table-column>
      <el-table-column v-if="canApprove" label="Status Update" width="180">
        <template #default="{ row }">
          <el-select v-model="row.status" placeholder="Status">
            <el-option label="open" value="open" />
            <el-option label="acknowledged" value="acknowledged" />
            <el-option label="closed" value="closed" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column v-if="canApprove" label="Actions" width="140">
        <template #default="{ row }">
          <el-button size="small" @click="saveAlert(row)">Save</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { api } from "../api/client";
import type { AlertOutWithQc, AlertUpdate } from "../api/contracts";
import { canApprove } from "../api/session";
import QCCommentThread from "../components/QCCommentThread.vue";

const alerts = ref<AlertOutWithQc[]>([]);

function formatSignalRules(alert: AlertOutWithQc): string {
  if (!alert.signals?.length) {
    return "-";
  }
  return alert.signals
    .map((signal) => signal.rule_variant ? `${signal.rule} (${signal.rule_variant})` : signal.rule)
    .join(", ");
}

async function loadAlerts() {
  alerts.value = await api.get<AlertOutWithQc[]>("/alerts");
}

async function saveAlert(row: AlertOutWithQc) {
  try {
    const reason = await ElMessageBox.prompt(
      "Reason",
      "Update Alert",
      {
        confirmButtonText: "Save",
        cancelButtonText: "Cancel",
        inputPlaceholder: "Review outcome or assignment rationale",
      }
    ).catch(() => null);
    if (!reason) {
      return;
    }
    const payload: AlertUpdate = {
      status: row.status ?? null,
      assigned_to: row.assigned_to ?? null,
      reason: reason.value,
    };
    await api.patch(`/alerts/${row.id}`, payload);
    ElMessage.success("Alert updated");
  } catch {
    ElMessage.error("Failed to update alert");
  }
}

onMounted(loadAlerts);
</script>

<style scoped>
.alert-evaluation-detail {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px 16px;
  margin-bottom: 12px;
}
.alert-evaluation-detail div { display: grid; gap: 3px; }
.alert-evaluation-detail span { color: #64748b; font-size: 12px; }
</style>
