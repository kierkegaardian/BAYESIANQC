<template>
  <div class="page alerts-page">
    <div class="page-header">
      <div><h2>Alerts</h2><div class="muted">Review QC conditions that need attention.</div></div>
      <div class="toolbar">
        <el-select v-model="statusFilter" clearable placeholder="All statuses" class="status-filter" @change="resetAndLoad">
          <el-option label="Open" value="open" /><el-option label="Acknowledged" value="acknowledged" /><el-option label="Closed" value="closed" />
        </el-select>
        <el-select v-model="dispositionFilter" clearable placeholder="All dispositions" class="status-filter" @change="resetAndLoad">
          <el-option label="Accept" value="accept" /><el-option label="Monitor" value="monitor" />
          <el-option label="Hold for review" value="hold-for-review" /><el-option label="Reject" value="reject" />
        </el-select>
        <el-select v-model="streamFilter" clearable filterable placeholder="All streams" class="stream-filter" @change="resetAndLoad">
          <el-option v-for="stream in streams" :key="stream.stream_id" :value="stream.stream_id" :label="streamLabel(stream.stream_id)" />
        </el-select>
        <el-date-picker v-model="dateRange" type="daterange" range-separator="to" start-placeholder="From" end-placeholder="To" @change="resetAndLoad" />
        <el-button :loading="loading" @click="loadAlerts">Refresh</el-button>
      </div>
    </div>

    <el-alert v-if="loadError" type="error" :closable="false" show-icon title="Alerts could not be loaded." class="section-card">
      <el-button size="small" @click="loadAlerts">Retry</el-button>
    </el-alert>

    <el-table v-loading="loading" :data="alerts" stripe class="full-width" empty-text="No alerts match this view">
      <el-table-column type="expand" width="48">
        <template #default="{ row }"><div class="comment-panel"><QCCommentThread target-type="alert" :target-id="row.id" title="Alert Comments" /></div></template>
      </el-table-column>
      <el-table-column label="Alert" min-width="150">
        <template #default="{ row }"><strong>{{ stakeholder ? "QC alert" : shortId(row.id) }}</strong><div class="small-text muted" :title="stakeholder ? undefined : row.id">{{ formatDate(row.qc_record_timestamp ?? row.created_at) }}</div></template>
      </el-table-column>
      <el-table-column label="QC stream" min-width="245">
        <template #default="{ row }"><span :title="row.stream_id">{{ streamLabel(row.stream_id) }}</span></template>
      </el-table-column>
      <el-table-column label="Disposition" min-width="125"><template #default="{ row }"><el-tag :type="dispositionTone(row.disposition)">{{ displayEnum(row.disposition) }}</el-tag></template></el-table-column>
      <el-table-column label="Predictive risk" min-width="130"><template #default="{ row }">{{ riskLabel(row) }}</template></el-table-column>
      <el-table-column label="Signals" min-width="140"><template #default="{ row }">{{ formatSignalRules(row) }}</template></el-table-column>
      <el-table-column label="Status" min-width="125"><template #default="{ row }"><el-tag>{{ displayEnum(row.status) }}</el-tag></template></el-table-column>
      <el-table-column v-if="canManageAlerts" label="Assignment" min-width="170"><template #default="{ row }"><el-input v-model="draftFor(row).assigned_to" placeholder="Assignee" /></template></el-table-column>
      <el-table-column v-if="canManageAlerts" label="New status" min-width="160">
        <template #default="{ row }"><el-select v-model="draftFor(row).status"><el-option label="Open" value="open" /><el-option label="Acknowledged" value="acknowledged" /><el-option label="Closed" value="closed" /></el-select></template>
      </el-table-column>
      <el-table-column v-if="canManageAlerts" label="Actions" width="110"><template #default="{ row }"><el-button size="small" :loading="savingId === row.id" :disabled="!changed(row)" @click="saveAlert(row)">Save</el-button></template></el-table-column>
    </el-table>

    <div class="pagination-row">
      <span class="muted">{{ total }} alert{{ total === 1 ? "" : "s" }}</span>
      <el-pagination v-model:current-page="currentPage" :page-size="pageSize" :total="total" layout="prev, pager, next" @current-change="loadAlerts" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { useRoute } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { api } from "../api/client";
import type { AlertOutWithQc, AlertStatus, AlertUpdate, StreamCatalogOut } from "../api/contracts";
import { canManageAlerts } from "../api/session";
import QCCommentThread from "../components/QCCommentThread.vue";
import { alertDraftChanged, ensureAlertDraft, resetAlertDraft, type AlertDraftMap } from "./alertDrafts";
import { availableRiskNumber, riskIsUnavailable, unavailableRiskReason } from "./bayesianRiskAvailability";
import { isStakeholderDeployment } from "../deployment";
import { loadStreamCatalog } from "../api/streamCatalog";

const route = useRoute();
const stakeholder = isStakeholderDeployment;
const alerts = ref<AlertOutWithQc[]>([]);
const streams = ref<StreamCatalogOut[]>([]);
const drafts = reactive<AlertDraftMap>({});
const loading = ref(false);
const loadError = ref(false);
const savingId = ref<string | null>(null);
const currentPage = ref(1);
const pageSize = 25;
const total = ref(0);
const initialStatus = Array.isArray(route.query.status) ? route.query.status[0] : route.query.status;
const statusFilter = ref<AlertStatus | "">(
  initialStatus === "open" || initialStatus === "acknowledged" || initialStatus === "closed" ? initialStatus : ""
);
const dispositionFilter = ref("");
const streamFilter = ref("");
const dateRange = ref<[Date, Date] | null>(null);

function syncDrafts(): void {
  for (const alert of alerts.value) resetAlertDraft(drafts, alert);
}
function draftFor(row: AlertOutWithQc) { return ensureAlertDraft(drafts, row); }
function changed(row: AlertOutWithQc): boolean { return alertDraftChanged(drafts, row); }
function formatSignalRules(alert: AlertOutWithQc): string { return alert.signals?.map((signal) => signal.rule).join(", ") || "None"; }
function shortId(id: string): string { return id.slice(0, 8); }
function formatDate(value: string | null | undefined): string { return value ? new Date(value).toLocaleString() : "Time unavailable"; }
function displayEnum(value: string | null | undefined): string { return value ? value.replaceAll("-", " ").replaceAll("_", " ") : "Not set"; }
function streamLabel(id: string): string { return id.replace(/^demo-/, "").replaceAll("_", " ").replaceAll("-", " "); }
function dispositionTone(value: string | null | undefined): "danger" | "warning" | "success" | "info" { return value === "reject" ? "danger" : value === "hold-for-review" || value === "monitor" ? "warning" : value === "accept" ? "success" : "info"; }
function riskLabel(row: AlertOutWithQc): string {
  if (riskIsUnavailable(row.bayesian_risk)) return `Bayesian inference unavailable — ${unavailableRiskReason(row.bayesian_risk)}`;
  const value = availableRiskNumber(row.bayesian_risk, "probability_outside_limits");
  return value === null ? "Not available" : `${(value * 100).toFixed(value * 100 < 10 ? 1 : 0)}% action risk`;
}

async function loadAlerts(): Promise<void> {
  loading.value = true; loadError.value = false;
  try {
    const params = new URLSearchParams({ limit: String(pageSize), offset: String((currentPage.value - 1) * pageSize) });
    if (statusFilter.value) params.set("status", statusFilter.value);
    if (dispositionFilter.value) params.set("disposition", dispositionFilter.value);
    if (streamFilter.value) params.set("stream", streamFilter.value);
    if (dateRange.value) {
      const [from, to] = dateRange.value;
      const end = new Date(to); end.setHours(23, 59, 59, 999);
      params.set("from", from.toISOString()); params.set("to", end.toISOString());
    }
    const page = await api.getPage<AlertOutWithQc>(`/alerts?${params}`);
    alerts.value = page.items; total.value = page.total; syncDrafts();
  } catch {
    alerts.value = [];
    total.value = 0;
    loadError.value = true;
  }
  finally { loading.value = false; }
}
function resetAndLoad(): void { currentPage.value = 1; void loadAlerts(); }

async function saveAlert(row: AlertOutWithQc): Promise<void> {
  if (savingId.value || !changed(row)) return;
  const prompt = await ElMessageBox.prompt("Explain the review or assignment decision.", "Update Alert", { inputPlaceholder: "Required reason" }).catch(() => null);
  if (!prompt?.value.trim()) return;
  savingId.value = row.id;
  try {
    const draft = draftFor(row);
    const payload: AlertUpdate = { status: draft.status, assigned_to: draft.assigned_to.trim() || null, reason: prompt.value.trim() };
    const saved = await api.patch<AlertOutWithQc>(`/alerts/${row.id}`, payload);
    alerts.value = alerts.value.map((item) => item.id === saved.id ? saved : item); syncDrafts(); ElMessage.success("Alert updated");
  } catch (error) { resetAlertDraft(drafts, row); ElMessage.error(error instanceof Error ? error.message : "Alert update failed"); }
  finally { savingId.value = null; }
}

onMounted(() => {
  void loadStreamCatalog().then((items) => { streams.value = items; }).catch(() => undefined);
  void loadAlerts();
});
</script>

<style scoped>
.alerts-page { max-width: 1500px; }
.status-filter { width: 170px; }
.stream-filter { width: 220px; }
.pagination-row { align-items: center; display: flex; gap: 16px; justify-content: space-between; padding: 16px 0; }
@media (max-width: 760px) { .pagination-row { align-items: flex-start; flex-direction: column; } }
</style>
