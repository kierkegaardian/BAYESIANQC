<template>
  <div class="page workflow-page">
    <div class="page-header">
      <div><h2>CAPAs</h2><div class="muted">Turn investigation findings into owned corrective and preventive actions.</div></div>
      <el-button v-if="canManageCapas" type="primary" @click="openCreate">New CAPA</el-button>
    </div>

    <el-alert v-if="loadError" type="error" :closable="false" show-icon class="section-card">
      <template #title>CAPAs could not be loaded.</template>
      <el-button size="small" @click="loadPage">Retry</el-button>
    </el-alert>
    <el-table v-loading="loading" :data="capas" stripe class="full-width" empty-text="No CAPAs yet">
      <el-table-column v-if="!stakeholder" prop="id" label="ID" width="80" />
      <el-table-column prop="status" label="Status" min-width="130" />
      <el-table-column prop="root_cause_category" label="Root cause" min-width="180" />
      <el-table-column label="Investigation" min-width="260">
        <template #default="{ row }">{{ investigationLabel(row.investigation_id) }}</template>
      </el-table-column>
      <el-table-column label="Alert" min-width="240">
        <template #default="{ row }">{{ alertLabel(row.alert_id) }}</template>
      </el-table-column>
      <el-table-column v-if="canManageCapas" label="Actions" width="100">
        <template #default="{ row }"><el-button size="small" @click="openEdit(row)">Edit</el-button></template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogOpen" :title="dialogTitle" width="min(620px, calc(100vw - 32px))">
      <el-alert v-if="saveError" type="error" :closable="false" show-icon :title="saveError" class="dialog-alert" />
      <el-form label-position="top">
        <el-form-item label="Linked alert">
          <el-select v-model="form.alert_id" filterable clearable :allow-create="!stakeholder" placeholder="Choose an alert" class="full-width">
            <el-option v-for="alert in alerts" :key="alert.id" :value="alert.id" :label="alertOptionLabel(alert)" />
          </el-select>
        </el-form-item>
        <el-form-item label="Linked investigation">
          <el-select v-model="form.investigation_id" filterable clearable :allow-create="!stakeholder" placeholder="Choose an investigation" class="full-width">
            <el-option v-for="item in investigations" :key="item.id" :value="String(item.id)" :label="investigationOptionLabel(item)" />
          </el-select>
        </el-form-item>
        <el-form-item label="Root cause category"><el-input v-model="form.root_cause_category" /></el-form-item>
        <el-form-item :label="stakeholder ? 'Corrective actions (one per line)' : 'Corrective actions (JSON list)'">
          <el-input v-model="form.corrective_actions" type="textarea" :rows="3" :placeholder="stakeholder ? 'Describe each corrective action on its own line' : '[]'" />
        </el-form-item>
        <el-form-item :label="stakeholder ? 'Preventive actions (one per line)' : 'Preventive actions (JSON list)'">
          <el-input v-model="form.preventive_actions" type="textarea" :rows="3" :placeholder="stakeholder ? 'Describe each preventive action on its own line' : '[]'" />
        </el-form-item>
        <el-form-item label="Owners (comma separated)"><el-input v-model="form.owners" /></el-form-item>
        <el-form-item label="Due date"><el-date-picker v-model="form.due_at" type="date" class="full-width" /></el-form-item>
        <el-form-item label="Verification plan"><el-input v-model="form.verification_plan" type="textarea" :rows="2" /></el-form-item>
        <el-form-item label="Status">
          <el-select v-model="form.status" class="full-width">
            <el-option label="Draft" value="draft" /><el-option label="Open" value="open" />
            <el-option label="Implementing" value="implementing" /><el-option label="Effectiveness check" value="effectiveness_check" />
            <el-option label="Closed" value="closed" /><el-option label="Reopened" value="reopened" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogOpen = false">Cancel</el-button>
        <el-button v-if="canManageCapas" type="primary" :loading="saving" @click="saveCapa">Save</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { api } from "../api/client";
import type { AlertOutWithQc, CapaIn, CapaOut, CapaStatus, InvestigationOut } from "../api/contracts";
import { canManageCapas } from "../api/session";
import { isStakeholderDeployment } from "../deployment";
import { formatCapaActions, parseCapaActions } from "./capaActions";

type CapaForm = {
  alert_id: string; investigation_id: string; root_cause_category: string;
  corrective_actions: string; preventive_actions: string; owners: string;
  due_at: Date | null; verification_plan: string; status: CapaStatus;
};

const stakeholder = isStakeholderDeployment;
const capas = ref<CapaOut[]>([]);
const alerts = ref<AlertOutWithQc[]>([]);
const investigations = ref<InvestigationOut[]>([]);
const dialogOpen = ref(false);
const dialogTitle = ref("New CAPA");
const editingId = ref<number | null>(null);
const loading = ref(false);
const saving = ref(false);
const loadError = ref(false);
const saveError = ref("");
const form = reactive<CapaForm>({
  alert_id: "", investigation_id: "", root_cause_category: "", corrective_actions: "",
  preventive_actions: "", owners: "", due_at: null, verification_plan: "", status: "draft",
});

function resetForm(): void {
  Object.assign(form, {
    alert_id: "", investigation_id: "", root_cause_category: "",
    corrective_actions: stakeholder ? "" : "[]", preventive_actions: stakeholder ? "" : "[]",
    owners: "", due_at: null, verification_plan: "", status: "draft",
  });
}
function shortText(value: string): string { return value.replace(/^demo-/, "").replaceAll("-", " ").replaceAll("_", " "); }
function alertOptionLabel(alert: AlertOutWithQc): string {
  return `${shortText(alert.stream_id)} · ${alert.status ?? "open"} · ${new Date(alert.qc_record_timestamp ?? alert.created_at).toLocaleDateString()}`;
}
function alertLabel(id: string | null | undefined): string {
  if (!id) return "No alert linked";
  const alert = alerts.value.find((item) => item.id === id);
  return alert ? alertOptionLabel(alert) : stakeholder ? "Linked alert unavailable" : id;
}
function investigationOptionLabel(item: InvestigationOut): string {
  const problem = item.problem_statement.length > 70 ? `${item.problem_statement.slice(0, 67)}...` : item.problem_statement;
  return `${problem} · ${shortText(item.status)}`;
}
function investigationLabel(id: number | null | undefined): string {
  if (!id) return "No investigation linked";
  const item = investigations.value.find((candidate) => candidate.id === id);
  return item ? investigationOptionLabel(item) : stakeholder ? "Linked investigation unavailable" : String(id);
}
async function loadPage(): Promise<void> {
  loading.value = true; loadError.value = false;
  try {
    [capas.value, alerts.value, investigations.value] = await Promise.all([
      api.get<CapaOut[]>("/capas"), api.get<AlertOutWithQc[]>("/alerts?limit=200"), api.get<InvestigationOut[]>("/investigations"),
    ]);
  } catch { capas.value = []; alerts.value = []; investigations.value = []; loadError.value = true; }
  finally { loading.value = false; }
}
function openCreate(): void { resetForm(); editingId.value = null; dialogTitle.value = "New CAPA"; saveError.value = ""; dialogOpen.value = true; }
function openEdit(row: CapaOut): void {
  editingId.value = row.id; dialogTitle.value = "Edit CAPA"; saveError.value = "";
  Object.assign(form, {
    alert_id: row.alert_id ?? "", investigation_id: row.investigation_id?.toString() ?? "",
    root_cause_category: row.root_cause_category ?? "", corrective_actions: formatCapaActions(row.corrective_actions ?? [], stakeholder),
    preventive_actions: formatCapaActions(row.preventive_actions ?? [], stakeholder), owners: (row.owners ?? []).join(", "),
    due_at: row.due_at ? new Date(row.due_at) : null, verification_plan: row.verification_plan ?? "", status: row.status,
  });
  dialogOpen.value = true;
}
async function saveCapa(): Promise<void> {
  if (!canManageCapas.value || saving.value) return;
  saveError.value = "";
  let payload: CapaIn;
  try {
    payload = {
      alert_id: form.alert_id || null, investigation_id: form.investigation_id ? Number(form.investigation_id) : null,
      root_cause_category: form.root_cause_category || null, corrective_actions: parseCapaActions(form.corrective_actions, stakeholder),
      preventive_actions: parseCapaActions(form.preventive_actions, stakeholder), owners: form.owners.split(",").map((item) => item.trim()).filter(Boolean),
      due_at: form.due_at?.toISOString() ?? null, verification_plan: form.verification_plan || null, status: form.status,
    };
  } catch (error) { saveError.value = error instanceof Error ? error.message : "Check the action fields"; return; }
  if (editingId.value !== null) {
    const reason = await ElMessageBox.prompt("Explain what changed.", "Update CAPA", { inputPlaceholder: "Required reason" }).catch(() => null);
    if (!reason?.value.trim()) return;
    payload.reason = reason.value.trim();
  }
  saving.value = true;
  try {
    if (editingId.value === null) await api.post("/capas", payload); else await api.patch(`/capas/${editingId.value}`, payload);
    ElMessage.success("CAPA saved"); dialogOpen.value = false; await loadPage();
  } catch (error) { saveError.value = error instanceof Error ? error.message : "Failed to save CAPA"; }
  finally { saving.value = false; }
}

onMounted(() => { void loadPage(); });
</script>

<style scoped>
.workflow-page { max-width: 1400px; }
.dialog-alert { margin-bottom: 12px; }
</style>
