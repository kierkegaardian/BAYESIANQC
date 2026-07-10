<template>
  <div class="page workflow-page">
    <div class="page-header">
      <div><h2>Investigations</h2><div class="muted">Document the review from alert to decision.</div></div>
      <el-button v-if="canManageInvestigations" type="primary" @click="openCreate">New Investigation</el-button>
    </div>

    <el-alert v-if="loadError" type="error" :closable="false" show-icon class="section-card">
      <template #title>Investigations could not be loaded.</template>
      <el-button size="small" @click="loadPage">Retry</el-button>
    </el-alert>
    <el-table v-loading="loading" :data="investigations" stripe class="full-width" empty-text="No investigations yet">
      <el-table-column v-if="!stakeholder" prop="id" label="ID" width="80" />
      <el-table-column prop="status" label="Status" min-width="110" />
      <el-table-column prop="problem_statement" label="Problem statement" min-width="260" />
      <el-table-column label="Linked alert" min-width="260">
        <template #default="{ row }">{{ alertLabel(row.alert_id) }}</template>
      </el-table-column>
      <el-table-column v-if="canManageInvestigations" label="Actions" width="100">
        <template #default="{ row }"><el-button size="small" @click="openEdit(row)">Edit</el-button></template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogOpen" :title="dialogTitle" width="min(560px, calc(100vw - 32px))">
      <el-alert v-if="saveError" type="error" :closable="false" show-icon :title="saveError" class="dialog-alert" />
      <el-form label-position="top">
        <el-form-item label="Linked alert">
          <el-select
            v-model="form.alert_id"
            filterable
            clearable
            :allow-create="!stakeholder"
            placeholder="Choose the alert being investigated"
            class="full-width"
          >
            <el-option v-for="alert in alerts" :key="alert.id" :value="alert.id" :label="alertOptionLabel(alert)" />
          </el-select>
        </el-form-item>
        <el-form-item label="Problem statement"><el-input v-model="form.problem_statement" type="textarea" :rows="2" /></el-form-item>
        <el-form-item label="Suspected cause"><el-input v-model="form.suspected_cause" type="textarea" :rows="2" /></el-form-item>
        <el-form-item label="Outcome"><el-input v-model="form.outcome" type="textarea" :rows="2" /></el-form-item>
        <el-form-item label="Decision"><el-input v-model="form.decision" type="textarea" :rows="2" /></el-form-item>
        <el-form-item label="Status">
          <el-select v-model="form.status" class="full-width">
            <el-option label="Open" value="open" /><el-option label="In review" value="in_review" /><el-option label="Closed" value="closed" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogOpen = false">Cancel</el-button>
        <el-button v-if="canManageInvestigations" type="primary" :loading="saving" @click="saveInvestigation">Save</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { api } from "../api/client";
import type { AlertOutWithQc, InvestigationIn, InvestigationOut, InvestigationStatus } from "../api/contracts";
import { canManageInvestigations } from "../api/session";
import { isStakeholderDeployment } from "../deployment";

type InvestigationForm = {
  alert_id: string;
  problem_statement: string;
  suspected_cause: string;
  outcome: string;
  decision: string;
  status: InvestigationStatus;
};

const stakeholder = isStakeholderDeployment;
const investigations = ref<InvestigationOut[]>([]);
const alerts = ref<AlertOutWithQc[]>([]);
const dialogOpen = ref(false);
const dialogTitle = ref("New Investigation");
const editingId = ref<number | null>(null);
const loading = ref(false);
const saving = ref(false);
const loadError = ref(false);
const saveError = ref("");
const form = reactive<InvestigationForm>({ alert_id: "", problem_statement: "", suspected_cause: "", outcome: "", decision: "", status: "open" });

function resetForm(): void {
  Object.assign(form, { alert_id: "", problem_statement: "", suspected_cause: "", outcome: "", decision: "", status: "open" });
}
function shortStream(value: string): string { return value.replace(/^demo-/, "").replaceAll("-", " ").replaceAll("_", " "); }
function alertOptionLabel(alert: AlertOutWithQc): string {
  const time = new Date(alert.qc_record_timestamp ?? alert.created_at).toLocaleDateString();
  return `${shortStream(alert.stream_id)} · ${alert.status ?? "open"} · ${time}`;
}
function alertLabel(id: string | null | undefined): string {
  if (!id) return "No alert linked";
  const alert = alerts.value.find((item) => item.id === id);
  return alert ? alertOptionLabel(alert) : stakeholder ? "Linked alert unavailable" : id;
}

async function loadPage(): Promise<void> {
  loading.value = true;
  loadError.value = false;
  try {
    [investigations.value, alerts.value] = await Promise.all([
      api.get<InvestigationOut[]>("/investigations"),
      api.get<AlertOutWithQc[]>("/alerts?limit=200"),
    ]);
  } catch { investigations.value = []; alerts.value = []; loadError.value = true; }
  finally { loading.value = false; }
}
function openCreate(): void {
  resetForm(); editingId.value = null; dialogTitle.value = "New Investigation"; saveError.value = ""; dialogOpen.value = true;
}
function openEdit(row: InvestigationOut): void {
  editingId.value = row.id; dialogTitle.value = "Edit Investigation"; saveError.value = "";
  Object.assign(form, {
    alert_id: row.alert_id ?? "", problem_statement: row.problem_statement,
    suspected_cause: row.suspected_cause ?? "", outcome: row.outcome ?? "",
    decision: row.decision ?? "", status: row.status,
  });
  dialogOpen.value = true;
}
async function saveInvestigation(): Promise<void> {
  if (!canManageInvestigations.value || saving.value) return;
  saveError.value = "";
  const payload: InvestigationIn = {
    alert_id: form.alert_id || null, problem_statement: form.problem_statement,
    suspected_cause: form.suspected_cause || null, outcome: form.outcome || null,
    decision: form.decision || null, status: form.status,
  };
  if (editingId.value !== null) {
    const reason = await ElMessageBox.prompt("Explain what changed.", "Update Investigation", { inputPlaceholder: "Required reason" }).catch(() => null);
    if (!reason?.value.trim()) return;
    payload.reason = reason.value.trim();
  }
  saving.value = true;
  try {
    if (editingId.value === null) await api.post("/investigations", payload);
    else await api.patch(`/investigations/${editingId.value}`, payload);
    ElMessage.success("Investigation saved"); dialogOpen.value = false; await loadPage();
  } catch (error) { saveError.value = error instanceof Error ? error.message : "Failed to save investigation"; }
  finally { saving.value = false; }
}

onMounted(() => { void loadPage(); });
</script>

<style scoped>
.workflow-page { max-width: 1300px; }
.dialog-alert { margin-bottom: 12px; }
</style>
