<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2>Analytes</h2>
        <div class="muted">Define analytes under methods.</div>
      </div>
      <el-button type="primary" @click="openCreate">Add Analyte</el-button>
    </div>

    <el-table :data="analytes" stripe class="full-width">
      <el-table-column prop="name" label="Name" />
      <el-table-column prop="method_id" label="Method ID" />
      <el-table-column prop="units" label="Units" />
      <el-table-column prop="active" label="Active" />
      <el-table-column label="Actions" width="140">
        <template #default="{ row }">
          <el-button size="small" @click="openEdit(row)">Edit</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogOpen" :title="dialogTitle" width="480px">
      <el-form label-position="top">
        <el-form-item label="Method">
          <el-select v-model="form.method_id" placeholder="Select method" class="full-width">
            <el-option
              v-for="method in methods"
              :key="method.id"
              :label="method.name"
              :value="method.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="Name">
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item label="Units">
          <el-input v-model="form.units" />
        </el-form-item>
        <el-form-item label="Active">
          <el-switch v-model="form.active" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogOpen = false">Cancel</el-button>
        <el-button type="primary" @click="saveAnalyte">Save</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { api } from "../api/client";

const methods = ref<any[]>([]);
const analytes = ref<any[]>([]);
const dialogOpen = ref(false);
const dialogTitle = ref("Add Analyte");
const editingId = ref<number | null>(null);

const form = reactive({
  name: "",
  method_id: null as number | null,
  units: "",
  active: true,
});

function resetForm() {
  form.name = "";
  form.method_id = null;
  form.units = "";
  form.active = true;
}

async function loadData() {
  methods.value = await api.get("/methods");
  analytes.value = await api.get("/analytes");
}

function openCreate() {
  resetForm();
  editingId.value = null;
  dialogTitle.value = "Add Analyte";
  dialogOpen.value = true;
}

function openEdit(row: any) {
  editingId.value = row.id;
  dialogTitle.value = "Edit Analyte";
  form.name = row.name;
  form.method_id = row.method_id;
  form.units = row.units || "";
  form.active = row.active;
  dialogOpen.value = true;
}

async function saveAnalyte() {
  try {
    if (editingId.value) {
      await api.patch(`/analytes/${editingId.value}`, form);
    } else {
      await api.post("/analytes", form);
    }
    ElMessage.success("Analyte saved");
    dialogOpen.value = false;
    analytes.value = await api.get("/analytes");
  } catch (error) {
    ElMessage.error("Failed to save analyte");
  }
}

onMounted(loadData);
</script>
