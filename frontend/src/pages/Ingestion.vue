<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2>QC Ingestion</h2>
        <div class="muted">Submit a single record or upload CSV.</div>
      </div>
      <el-button @click="loadStreams">Reload Streams</el-button>
    </div>

    <el-card style="margin-bottom: 20px">
      <h3>Single Record</h3>
      <el-form label-position="top" class="toolbar">
        <el-form-item label="Stream">
          <el-select v-model="form.stream_id" placeholder="Select stream" class="full-width">
            <el-option
              v-for="stream in streams"
              :key="stream.stream_id"
              :label="stream.stream_id"
              :value="stream.stream_id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="Result Value">
          <el-input-number v-model="form.result_value" class="full-width" :step="0.1" />
        </el-form-item>
        <el-form-item label="Timestamp">
          <el-date-picker v-model="form.timestamp" type="datetime" class="full-width" />
        </el-form-item>
        <el-form-item label="Entry Source">
          <el-select v-model="form.entry_source" class="full-width">
            <el-option label="manual" value="manual" />
            <el-option label="automated" value="automated" />
          </el-select>
        </el-form-item>
        <el-form-item label="Comments">
          <el-input v-model="form.comments" />
        </el-form-item>
        <el-form-item label="Idempotency Key">
          <el-input v-model="form.idempotency_key" />
        </el-form-item>
      </el-form>
      <el-button type="primary" @click="submitRecord">Submit</el-button>
    </el-card>

    <el-card>
      <h3>CSV Upload</h3>
      <el-upload
        class="upload"
        drag
        action=""
        :http-request="uploadCsv"
        :show-file-list="false"
      >
        <div class="el-upload__text">Drop CSV here or click to upload</div>
      </el-upload>
      <div v-if="uploadSummary" class="muted" style="margin-top: 12px">
        {{ uploadSummary }}
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { api } from "../api/client";

const streams = ref<any[]>([]);
const uploadSummary = ref<string | null>(null);

const form = reactive({
  stream_id: "",
  result_value: 0,
  timestamp: new Date(),
  entry_source: "manual",
  comments: "",
  idempotency_key: "",
});

watch(
  () => form.stream_id,
  (value) => {
    const stream = streams.value.find((item) => item.stream_id === value);
    if (stream) {
      form.result_value = stream.target_value;
    }
  }
);

async function loadStreams() {
  streams.value = await api.get("/streams");
}

async function submitRecord() {
  const stream = streams.value.find((item) => item.stream_id === form.stream_id);
  if (!stream) {
    ElMessage.error("Select a stream first");
    return;
  }
  const payload = {
    stream_id: stream.stream_id,
    result_value: form.result_value,
    timestamp: new Date(form.timestamp).toISOString(),
    analyte: stream.analyte,
    qc_level: stream.qc_level,
    instrument_id: stream.instrument,
    method_id: stream.method,
    operator_id: "ui-user",
    reagent_lot: null,
    control_material_lot: stream.control_material_lot,
    calibration_status: "ok",
    run_id: `ui-${Date.now()}`,
    units: stream.units,
    flags: [],
    entry_source: form.entry_source,
    comments: form.comments,
  };
  try {
    const headers = form.idempotency_key
      ? { "Idempotency-Key": form.idempotency_key }
      : undefined;
    await api.post("/qc/records", payload, headers);
    ElMessage.success("Record ingested");
  } catch (error) {
    const message =
      error instanceof Error && error.message
        ? error.message
        : "Failed to ingest record";
    ElMessage.error(message);
  }
}

async function uploadCsv(options: any) {
  try {
    const formData = new FormData();
    formData.append("file", options.file);
    const response = await api.upload("/qc/records/csv", formData);
    uploadSummary.value = `Accepted: ${response.accepted}, Errors: ${response.errors.length}`;
    ElMessage.success("CSV processed");
  } catch (error) {
    const message =
      error instanceof Error && error.message ? error.message : "CSV upload failed";
    ElMessage.error(message);
  }
}

onMounted(loadStreams);
</script>
