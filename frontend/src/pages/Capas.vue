<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2>CAPAs</h2>
        <div class="muted">Corrective and preventive action tracking.</div>
      </div>
      <el-button type="primary" @click="openCreate">New CAPA</el-button>
    </div>

    <el-table :data="capas" stripe class="full-width">
      <el-table-column prop="id" label="ID" width="80" />
      <el-table-column prop="status" label="Status" />
      <el-table-column prop="root_cause_category" label="Root Cause" />
      <el-table-column prop="alert_id" label="Alert ID" />
      <el-table-column prop="investigation_id" label="Investigation ID" />
      <el-table-column label="Actions" width="140">
        <template #default="{ row }">
          <el-button size="small" @click="openEdit(row)">Edit</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogOpen" :title="dialogTitle" width="520px">
      <el-form label-position="top">
        <el-form-item label="Alert ID">
          <el-input v-model="form.alert_id" placeholder="Optional alert id" />
        </el-form-item>
        <el-form-item label="Investigation ID">
          <el-input v-model="form.investigation_id" placeholder="Optional investigation id" />
        </el-form-item>
        <el-form-item label="Root Cause Category">
          <el-input v-model="form.root_cause_category" />
        </el-form-item>
        <el-form-item label="Corrective Actions (JSON list)">
          <el-input v-model="form.corrective_actions" />
        </el-form-item>
        <el-form-item label="Preventive Actions (JSON list)">
          <el-input v-model="form.preventive_actions" />
        </el-form-item>
        <el-form-item label="Owners (comma separated)">
          <el-input v-model="form.owners" />
        </el-form-item>
        <el-form-item label="Due Date">
          <el-date-picker v-model="form.due_at" type="date" class="full-width" />
        </el-form-item>
        <el-form-item label="Verification Plan">
          <el-input v-model="form.verification_plan" />
        </el-form-item>
        <el-form-item label="Status">
          <el-select v-model="form.status">
            <el-option label="draft" value="draft" />
            <el-option label="open" value="open" />
            <el-option label="implementing" value="implementing" />
            <el-option label="effectiveness_check" value="effectiveness_check" />
            <el-option label="closed" value="closed" />
            <el-option label="reopened" value="reopened" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogOpen = false">Cancel</el-button>
        <el-button type="primary" @click="saveCapa">Save</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { api } from "../api/client";

const capas = ref<any[]>([]);
const dialogOpen = ref(false);
const dialogTitle = ref("New CAPA");
const editingId = ref<number | null>(null);

const form = reactive({
  alert_id: "",
  investigation_id: "",
  root_cause_category: "",
  corrective_actions: "[]",
  preventive_actions: "[]",
  owners: "",
  due_at: null as Date | null,
  verification_plan: "",
  status: "draft",
});

function resetForm() {
  form.alert_id = "";
  form.investigation_id = "";
  form.root_cause_category = "";
  form.corrective_actions = "[]";
  form.preventive_actions = "[]";
  form.owners = "";
  form.due_at = null;
  form.verification_plan = "";
  form.status = "draft";
}

async function loadCapas() {
  capas.value = await api.get("/capas");
}

function openCreate() {
  resetForm();
  editingId.value = null;
  dialogTitle.value = "New CAPA";
  dialogOpen.value = true;
}

function openEdit(row: any) {
  editingId.value = row.id;
  dialogTitle.value = "Edit CAPA";
  form.alert_id = row.alert_id || "";
  form.investigation_id = row.investigation_id || "";
  form.root_cause_category = row.root_cause_category || "";
  form.corrective_actions = JSON.stringify(row.corrective_actions || []);
  form.preventive_actions = JSON.stringify(row.preventive_actions || []);
  form.owners = (row.owners || []).join(", ");
  form.due_at = row.due_at ? new Date(row.due_at) : null;
  form.verification_plan = row.verification_plan || "";
  form.status = row.status || "draft";
  dialogOpen.value = true;
}

function parseJsonList(value: string) {
  try {
    return JSON.parse(value);
  } catch {
    return [];
  }
}

async function saveCapa() {
  const payload = {
    alert_id: form.alert_id || null,
    investigation_id: form.investigation_id ? Number(form.investigation_id) : null,
    root_cause_category: form.root_cause_category || null,
    corrective_actions: parseJsonList(form.corrective_actions),
    preventive_actions: parseJsonList(form.preventive_actions),
    owners: form.owners ? form.owners.split(",").map((item) => item.trim()) : [],
    due_at: form.due_at ? form.due_at.toISOString() : null,
    verification_plan: form.verification_plan || null,
    status: form.status,
  };
  try {
    if (editingId.value) {
      await api.patch(`/capas/${editingId.value}`, payload);
    } else {
      await api.post("/capas", payload);
    }
    ElMessage.success("CAPA saved");
    dialogOpen.value = false;
    await loadCapas();
  } catch (error) {
    ElMessage.error("Failed to save CAPA");
  }
}

onMounted(loadCapas);
</script>
