<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2>Methods</h2>
        <div class="muted">Create methods tied to instruments.</div>
      </div>
      <el-button type="primary" @click="openCreate">Add Method</el-button>
    </div>

    <el-table :data="methods" stripe class="full-width">
      <el-table-column prop="name" label="Name" />
      <el-table-column prop="instrument_id" label="Instrument ID" />
      <el-table-column prop="technique" label="Technique" />
      <el-table-column prop="active" label="Active" />
      <el-table-column label="Actions" width="140">
        <template #default="{ row }">
          <el-button size="small" @click="openEdit(row)">Edit</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogOpen" :title="dialogTitle" width="480px">
      <el-form label-position="top">
        <el-form-item label="Instrument">
          <el-select v-model="form.instrument_id" placeholder="Select instrument" class="full-width">
            <el-option
              v-for="instrument in instruments"
              :key="instrument.id"
              :label="instrument.name"
              :value="instrument.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="Name">
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item label="Technique">
          <el-input v-model="form.technique" />
        </el-form-item>
        <el-form-item label="Active">
          <el-switch v-model="form.active" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogOpen = false">Cancel</el-button>
        <el-button type="primary" @click="saveMethod">Save</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { api } from "../api/client";

const instruments = ref<any[]>([]);
const methods = ref<any[]>([]);
const dialogOpen = ref(false);
const dialogTitle = ref("Add Method");
const editingId = ref<number | null>(null);

const form = reactive({
  name: "",
  instrument_id: null as number | null,
  technique: "",
  active: true,
});

function resetForm() {
  form.name = "";
  form.instrument_id = null;
  form.technique = "";
  form.active = true;
}

async function loadData() {
  instruments.value = await api.get("/instruments");
  methods.value = await api.get("/methods");
}

function openCreate() {
  resetForm();
  editingId.value = null;
  dialogTitle.value = "Add Method";
  dialogOpen.value = true;
}

function openEdit(row: any) {
  editingId.value = row.id;
  dialogTitle.value = "Edit Method";
  form.name = row.name;
  form.instrument_id = row.instrument_id;
  form.technique = row.technique || "";
  form.active = row.active;
  dialogOpen.value = true;
}

async function saveMethod() {
  try {
    if (editingId.value) {
      await api.patch(`/methods/${editingId.value}`, form);
    } else {
      await api.post("/methods", form);
    }
    ElMessage.success("Method saved");
    dialogOpen.value = false;
    methods.value = await api.get("/methods");
  } catch (error) {
    ElMessage.error("Failed to save method");
  }
}

onMounted(loadData);
</script>
