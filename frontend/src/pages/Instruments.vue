<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2>Instruments</h2>
        <div class="muted">Manage instrument inventory used by QC streams.</div>
      </div>
      <el-button type="primary" @click="openCreate">Add Instrument</el-button>
    </div>

    <el-table :data="instruments" stripe class="full-width">
      <el-table-column prop="name" label="Name" />
      <el-table-column prop="manufacturer" label="Manufacturer" />
      <el-table-column prop="model" label="Model" />
      <el-table-column prop="site" label="Site" />
      <el-table-column prop="active" label="Active" />
      <el-table-column label="Actions" width="140">
        <template #default="{ row }">
          <el-button size="small" @click="openEdit(row)">Edit</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogOpen" :title="dialogTitle" width="480px">
      <el-form label-position="top">
        <el-form-item label="Name">
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item label="Manufacturer">
          <el-input v-model="form.manufacturer" />
        </el-form-item>
        <el-form-item label="Model">
          <el-input v-model="form.model" />
        </el-form-item>
        <el-form-item label="Site">
          <el-input v-model="form.site" />
        </el-form-item>
        <el-form-item label="Active">
          <el-switch v-model="form.active" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogOpen = false">Cancel</el-button>
        <el-button type="primary" @click="saveInstrument">Save</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { api } from "../api/client";

const instruments = ref([]);
const dialogOpen = ref(false);
const dialogTitle = ref("Add Instrument");
const editingId = ref<number | null>(null);

const form = reactive({
  name: "",
  manufacturer: "",
  model: "",
  site: "",
  active: true,
});

function resetForm() {
  form.name = "";
  form.manufacturer = "";
  form.model = "";
  form.site = "";
  form.active = true;
}

async function loadInstruments() {
  instruments.value = await api.get("/instruments");
}

function openCreate() {
  resetForm();
  editingId.value = null;
  dialogTitle.value = "Add Instrument";
  dialogOpen.value = true;
}

function openEdit(row: any) {
  editingId.value = row.id;
  dialogTitle.value = "Edit Instrument";
  form.name = row.name;
  form.manufacturer = row.manufacturer || "";
  form.model = row.model || "";
  form.site = row.site || "";
  form.active = row.active;
  dialogOpen.value = true;
}

async function saveInstrument() {
  try {
    if (editingId.value) {
      await api.patch(`/instruments/${editingId.value}`, form);
    } else {
      await api.post("/instruments", form);
    }
    ElMessage.success("Instrument saved");
    dialogOpen.value = false;
    await loadInstruments();
  } catch (error) {
    ElMessage.error("Failed to save instrument");
  }
}

onMounted(loadInstruments);
</script>
