<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2>QC Events</h2>
        <div class="muted">Log calibration, maintenance, and lot changes.</div>
      </div>
      <el-button type="primary" @click="openCreate">Add Event</el-button>
    </div>

    <el-table :data="events" stripe class="full-width">
      <el-table-column prop="id" label="ID" width="80" />
      <el-table-column prop="event_type" label="Type" />
      <el-table-column prop="stream_id" label="Stream" />
      <el-table-column prop="timestamp" label="Timestamp" />
      <el-table-column prop="instrument_id" label="Instrument" />
    </el-table>

    <el-dialog v-model="dialogOpen" title="New Event" width="520px">
      <el-form label-position="top">
        <el-form-item label="Stream ID">
          <el-input v-model="form.stream_id" />
        </el-form-item>
        <el-form-item label="Event Type">
          <el-select v-model="form.event_type" class="full-width">
            <el-option label="calibration" value="calibration" />
            <el-option label="maintenance" value="maintenance" />
            <el-option label="reagent_lot_change" value="reagent_lot_change" />
            <el-option label="control_material_lot_change" value="control_material_lot_change" />
            <el-option label="software_update" value="software_update" />
            <el-option label="environmental_alert" value="environmental_alert" />
          </el-select>
        </el-form-item>
        <el-form-item label="Timestamp">
          <el-date-picker v-model="form.timestamp" type="datetime" class="full-width" />
        </el-form-item>
        <el-form-item label="Instrument ID">
          <el-input v-model="form.instrument_id" />
        </el-form-item>
        <el-form-item label="Metadata (JSON)">
          <el-input v-model="form.metadata" type="textarea" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogOpen = false">Cancel</el-button>
        <el-button type="primary" @click="saveEvent">Save</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { api } from "../api/client";

const events = ref<any[]>([]);
const dialogOpen = ref(false);

const form = reactive({
  stream_id: "",
  event_type: "calibration",
  timestamp: new Date(),
  instrument_id: "",
  metadata: "{}",
});

async function loadEvents() {
  events.value = await api.get("/qc/events");
}

function openCreate() {
  form.stream_id = "";
  form.event_type = "calibration";
  form.timestamp = new Date();
  form.instrument_id = "";
  form.metadata = "{}";
  dialogOpen.value = true;
}

function parseJson(value: string) {
  try {
    return JSON.parse(value);
  } catch {
    return {};
  }
}

async function saveEvent() {
  const payload = {
    stream_id: form.stream_id || null,
    event_type: form.event_type,
    timestamp: new Date(form.timestamp).toISOString(),
    instrument_id: form.instrument_id || null,
    metadata: parseJson(form.metadata),
  };
  try {
    await api.post("/qc/events", payload);
    ElMessage.success("Event created");
    dialogOpen.value = false;
    await loadEvents();
  } catch (error) {
    ElMessage.error("Failed to create event");
  }
}

onMounted(loadEvents);
</script>
