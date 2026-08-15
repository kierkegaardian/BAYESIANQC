<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2>QC Streams</h2>
        <div class="muted">Configure analyte + method + instrument streams.</div>
      </div>
      <el-button v-if="canEditConfig" type="primary" @click="openCreate">Add Stream</el-button>
    </div>

    <el-table :data="streams" stripe class="full-width">
      <el-table-column prop="stream_id" label="Stream ID" />
      <el-table-column prop="analyte" label="Analyte" />
      <el-table-column prop="method" label="Method" />
      <el-table-column prop="instrument" label="Instrument" />
      <el-table-column prop="qc_level" label="QC Level" />
      <el-table-column prop="units" label="Units" />
      <el-table-column prop="target_value" label="Target" />
      <el-table-column prop="sigma" label="Sigma" />
      <el-table-column label="Actions" width="160">
        <template #default="{ row }">
          <el-button size="small" @click="viewVersions(row)">Versions</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogOpen" title="Add Stream" width="560px">
      <el-form label-position="top">
        <el-form-item label="Stream ID">
          <el-input v-model="form.stream_id" />
        </el-form-item>
        <el-form-item label="Instrument">
          <el-select v-model="form.instrument" placeholder="Select instrument" class="full-width">
            <el-option
              v-for="instrument in instruments"
              :key="instrument.id"
              :label="instrument.name"
              :value="instrument.name"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="Method">
          <el-select v-model="form.method" placeholder="Select method" class="full-width">
            <el-option
              v-for="method in filteredMethods"
              :key="method.id"
              :label="method.name"
              :value="method.name"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="Analyte">
          <el-select v-model="form.analyte" placeholder="Select analyte" class="full-width">
            <el-option
              v-for="analyte in filteredAnalytes"
              :key="analyte.id"
              :label="analyte.name"
              :value="analyte.name"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="QC Level">
          <el-input v-model="form.qc_level" />
        </el-form-item>
        <el-form-item label="Control Material Lot">
          <el-input v-model="form.control_material_lot" />
        </el-form-item>
        <el-form-item label="Units">
          <el-input v-model="form.units" />
        </el-form-item>
        <el-form-item label="Target Value">
          <el-input-number v-model="form.target_value" class="full-width" :step="0.1" />
        </el-form-item>
        <el-form-item label="Sigma">
          <el-input-number v-model="form.sigma" class="full-width" :step="0.01" />
        </el-form-item>
        <el-form-item label="Warning Limit (SD)">
          <el-input-number v-model="form.warning_limit_sd" class="full-width" :step="0.1" />
        </el-form-item>
        <el-form-item label="Action Limit (SD)">
          <el-input-number v-model="form.action_limit_sd" class="full-width" :step="0.1" />
        </el-form-item>
        <el-form-item label="Risk Warn Threshold">
          <el-input-number v-model="form.risk_threshold_warn" class="full-width" :step="1" />
        </el-form-item>
        <el-form-item label="Risk Hold Threshold">
          <el-input-number v-model="form.risk_threshold_hold" class="full-width" :step="1" />
        </el-form-item>
        <el-form-item label="Bayesian Warn Threshold (P outside ±2 SD)">
          <el-input-number
            v-model="form.bayes_warn_prob_threshold"
            class="full-width"
            :step="0.05"
            :min="0"
            :max="1"
          />
        </el-form-item>
        <el-form-item label="Bayesian Warn Persistence (N consecutive)">
          <el-input-number v-model="form.bayes_warn_consecutive" class="full-width" :step="1" :min="1" />
        </el-form-item>
        <el-form-item label="Bayesian Hold Threshold (P outside ±3 SD)">
          <el-input-number
            v-model="form.bayes_hold_prob_threshold"
            class="full-width"
            :step="0.05"
            :min="0"
            :max="1"
          />
        </el-form-item>
        <el-form-item label="Bayesian Hold Persistence (N consecutive)">
          <el-input-number v-model="form.bayes_hold_consecutive" class="full-width" :step="1" :min="1" />
        </el-form-item>
        <el-form-item label="Minimum Value">
          <el-input-number v-model="form.min_value" class="full-width" :step="0.1" />
        </el-form-item>
        <el-form-item label="Maximum Value">
          <el-input-number v-model="form.max_value" class="full-width" :step="0.1" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogOpen = false">Cancel</el-button>
        <el-button v-if="canEditConfig" type="primary" @click="saveStream">Save</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="versionsOpen" title="Stream Versions" width="640px">
      <el-table :data="versions" stripe class="full-width">
        <el-table-column prop="version" label="Version" width="80" />
        <el-table-column prop="effective_from" label="Effective" />
        <el-table-column prop="target_value" label="Target" />
        <el-table-column prop="sigma" label="Sigma" />
        <el-table-column prop="warning_limit_sd" label="Warn SD" />
        <el-table-column prop="action_limit_sd" label="Action SD" />
      </el-table>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { api } from "../api/client";
import { canEditConfig } from "../api/session";
import type {
  AnalyteOut,
  InstrumentOut,
  MethodOut,
  StreamConfigIn,
  StreamConfigOut,
} from "../api/contracts";

const instruments = ref<InstrumentOut[]>([]);
const methods = ref<MethodOut[]>([]);
const analytes = ref<AnalyteOut[]>([]);
const streams = ref<StreamConfigOut[]>([]);
const dialogOpen = ref(false);
const versionsOpen = ref(false);
const versions = ref<StreamConfigOut[]>([]);

const form = reactive<StreamConfigIn>({
  stream_id: "",
  instrument: "",
  method: "",
  analyte: "",
  qc_level: "Level 1",
  control_material_lot: "",
  units: "",
  target_value: 0,
  sigma: 0.1,
  warning_limit_sd: 2,
  action_limit_sd: 3,
  control_limit_source: "configured",
  risk_threshold_warn: 50,
  risk_threshold_hold: 80,
  bayes_warn_prob_threshold: 0.25,
  bayes_warn_consecutive: 1,
  bayes_hold_prob_threshold: 0.8,
  bayes_hold_consecutive: 2,
  min_value: null,
  max_value: null,
});

const filteredMethods = computed(() => {
  const instrument = instruments.value.find((item) => item.name === form.instrument);
  if (!instrument) {
    return methods.value;
  }
  return methods.value.filter((method) => method.instrument_id === instrument.id);
});

const filteredAnalytes = computed(() => {
  const method = methods.value.find((item) => item.name === form.method);
  if (!method) {
    return analytes.value;
  }
  return analytes.value.filter((analyte) => analyte.method_id === method.id);
});

watch(
  () => form.instrument,
  () => {
    form.method = "";
    form.analyte = "";
  }
);

watch(
  () => form.method,
  () => {
    form.analyte = "";
  }
);

watch(
  () => form.analyte,
  (value) => {
    const analyte = analytes.value.find((item) => item.name === value);
    if (analyte && analyte.units) {
      form.units = analyte.units;
    }
  }
);

async function loadData() {
  instruments.value = await api.get<InstrumentOut[]>("/instruments");
  methods.value = await api.get<MethodOut[]>("/methods");
  analytes.value = await api.get<AnalyteOut[]>("/analytes");
  streams.value = await api.get<StreamConfigOut[]>("/streams");
}

function openCreate() {
  form.stream_id = "";
  form.instrument = "";
  form.method = "";
  form.analyte = "";
  form.qc_level = "Level 1";
  form.control_material_lot = "";
  form.units = "";
  form.target_value = 0;
  form.sigma = 0.1;
  form.warning_limit_sd = 2;
  form.action_limit_sd = 3;
  form.risk_threshold_warn = 50;
  form.risk_threshold_hold = 80;
  form.bayes_warn_prob_threshold = 0.25;
  form.bayes_warn_consecutive = 1;
  form.bayes_hold_prob_threshold = 0.8;
  form.bayes_hold_consecutive = 2;
  form.min_value = null;
  form.max_value = null;
  dialogOpen.value = true;
}

async function saveStream() {
  try {
    await api.post("/streams", form);
    ElMessage.success("Stream created");
    dialogOpen.value = false;
    streams.value = await api.get<StreamConfigOut[]>("/streams");
  } catch {
    ElMessage.error("Failed to create stream");
  }
}

async function viewVersions(row: StreamConfigOut) {
  versionsOpen.value = true;
  versions.value = await api.get<StreamConfigOut[]>(
    `/streams/${row.stream_id}/configs`
  );
}

onMounted(loadData);
</script>
