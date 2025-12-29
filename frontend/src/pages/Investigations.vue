<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2>Investigations</h2>
        <div class="muted">Track investigations linked to alerts.</div>
      </div>
      <el-button type="primary" @click="openCreate">New Investigation</el-button>
    </div>

    <el-table :data="investigations" stripe class="full-width">
      <el-table-column prop="id" label="ID" width="80" />
      <el-table-column prop="status" label="Status" />
      <el-table-column prop="problem_statement" label="Problem Statement" />
      <el-table-column prop="alert_id" label="Alert ID" />
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
        <el-form-item label="Problem Statement">
          <el-input v-model="form.problem_statement" />
        </el-form-item>
        <el-form-item label="Suspected Cause">
          <el-input v-model="form.suspected_cause" />
        </el-form-item>
        <el-form-item label="Outcome">
          <el-input v-model="form.outcome" />
        </el-form-item>
        <el-form-item label="Decision">
          <el-input v-model="form.decision" />
        </el-form-item>
        <el-form-item label="Status">
          <el-select v-model="form.status">
            <el-option label="open" value="open" />
            <el-option label="in_review" value="in_review" />
            <el-option label="closed" value="closed" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogOpen = false">Cancel</el-button>
        <el-button type="primary" @click="saveInvestigation">Save</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { api } from "../api/client";

const investigations = ref<any[]>([]);
const dialogOpen = ref(false);
const dialogTitle = ref("New Investigation");
const editingId = ref<number | null>(null);

const form = reactive({
  alert_id: "",
  problem_statement: "",
  suspected_cause: "",
  outcome: "",
  decision: "",
  status: "open",
});

function resetForm() {
  form.alert_id = "";
  form.problem_statement = "";
  form.suspected_cause = "";
  form.outcome = "";
  form.decision = "";
  form.status = "open";
}

async function loadInvestigations() {
  investigations.value = await api.get("/investigations");
}

function openCreate() {
  resetForm();
  editingId.value = null;
  dialogTitle.value = "New Investigation";
  dialogOpen.value = true;
}

function openEdit(row: any) {
  editingId.value = row.id;
  dialogTitle.value = "Edit Investigation";
  form.alert_id = row.alert_id || "";
  form.problem_statement = row.problem_statement;
  form.suspected_cause = row.suspected_cause || "";
  form.outcome = row.outcome || "";
  form.decision = row.decision || "";
  form.status = row.status || "open";
  dialogOpen.value = true;
}

async function saveInvestigation() {
  try {
    if (editingId.value) {
      await api.patch(`/investigations/${editingId.value}`, form);
    } else {
      await api.post("/investigations", form);
    }
    ElMessage.success("Investigation saved");
    dialogOpen.value = false;
    await loadInvestigations();
  } catch (error) {
    ElMessage.error("Failed to save investigation");
  }
}

onMounted(loadInvestigations);
</script>
