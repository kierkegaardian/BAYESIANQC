<template>
  <div class="page datastream-page">
    <div class="page-header">
      <div>
        <h2>Add Datastream</h2>
        <div class="muted">Create or reuse the objects behind one chartable QC stream.</div>
      </div>
      <el-button @click="downloadTemplate">Download XLSX Template</el-button>
    </div>

    <el-steps :active="step" finish-status="success" class="setup-steps">
      <el-step title="Location" />
      <el-step title="Method" />
      <el-step title="Limits" />
      <el-step title="Kiosk" />
      <el-step title="Review" />
    </el-steps>

    <section v-if="step === 0" class="setup-panel">
      <div class="form-grid">
        <el-form-item label="Enterprise Site"><el-input v-model="draft.site" /></el-form-item>
        <el-form-item label="Lab Bench / Area"><el-input v-model="draft.lab_bench" /></el-form-item>
        <el-form-item label="Instrument"><el-input v-model="draft.instrument_name" /></el-form-item>
        <el-form-item label="Manufacturer"><el-input v-model="draft.instrument_manufacturer" /></el-form-item>
        <el-form-item label="Model"><el-input v-model="draft.instrument_model" /></el-form-item>
      </div>
    </section>

    <section v-else-if="step === 1" class="setup-panel">
      <div class="form-grid">
        <el-form-item label="Method"><el-input v-model="draft.method_name" /></el-form-item>
        <el-form-item label="Technique"><el-input v-model="draft.method_technique" /></el-form-item>
        <el-form-item label="Parameter / Analyte"><el-input v-model="draft.parameter_name" /></el-form-item>
        <el-form-item label="Units"><el-input v-model="draft.units" /></el-form-item>
        <el-form-item label="Control Material"><el-input v-model="draft.material_name" /></el-form-item>
        <el-form-item label="Material Manufacturer"><el-input v-model="draft.material_manufacturer" /></el-form-item>
        <el-form-item label="Matrix"><el-input v-model="draft.matrix" /></el-form-item>
        <el-form-item label="QC Level"><el-input v-model="draft.qc_level" /></el-form-item>
        <el-form-item label="Control Material Lot"><el-input v-model="draft.control_material_lot" /></el-form-item>
      </div>
      <el-form-item label="Stream ID">
        <el-input v-model="draft.stream_id" :placeholder="generatedId" />
      </el-form-item>
    </section>

    <section v-else-if="step === 2" class="setup-panel">
      <div class="form-grid">
        <el-form-item label="Target Value"><el-input-number v-model="draft.target_value" class="full-width" :step="0.1" /></el-form-item>
        <el-form-item label="Sigma"><el-input-number v-model="draft.sigma" class="full-width" :step="0.01" :min="0.000001" /></el-form-item>
        <el-form-item label="Warning Limit SD"><el-input-number v-model="draft.warning_limit_sd" class="full-width" :step="0.1" /></el-form-item>
        <el-form-item label="Action Limit SD"><el-input-number v-model="draft.action_limit_sd" class="full-width" :step="0.1" /></el-form-item>
        <el-form-item label="Minimum Value"><el-input-number v-model="draft.min_value" class="full-width" :step="0.1" /></el-form-item>
        <el-form-item label="Maximum Value"><el-input-number v-model="draft.max_value" class="full-width" :step="0.1" /></el-form-item>
        <el-form-item label="Prior Mean"><el-input-number v-model="draft.prior_mu0" class="full-width" :placeholder="String(draft.target_value)" /></el-form-item>
        <el-form-item label="Prior Kappa"><el-input-number v-model="draft.prior_kappa0" class="full-width" :min="0.000001" /></el-form-item>
        <el-form-item label="Prior Alpha"><el-input-number v-model="draft.prior_alpha0" class="full-width" :min="1.000001" /></el-form-item>
        <el-form-item label="Prior Beta"><el-input-number v-model="draft.prior_beta0" class="full-width" :placeholder="String(defaultPriorBeta)" /></el-form-item>
      </div>
      <el-form-item label="Version Reason">
        <el-input v-model="draft.config_reason" />
      </el-form-item>
    </section>

    <section v-else-if="step === 3" class="setup-panel">
      <el-checkbox v-model="draft.kiosk_enabled">Assign this datastream to a saved kiosk</el-checkbox>
      <div v-if="draft.kiosk_enabled" class="form-grid kiosk-fields">
        <el-form-item label="Kiosk">
          <el-select v-model="draft.kiosk_slug" filterable allow-create default-first-option class="full-width">
            <el-option v-for="kiosk in kiosks" :key="kiosk.slug" :label="kiosk.label" :value="kiosk.slug" />
          </el-select>
        </el-form-item>
        <el-form-item label="Kiosk Label"><el-input v-model="draft.kiosk_label" /></el-form-item>
        <el-form-item label="Panel Title"><el-input v-model="draft.panel_title" :placeholder="`${draft.parameter_name} - ${draft.instrument_name}`" /></el-form-item>
        <el-form-item label="Start Date"><el-input v-model="draft.panel_start" placeholder="YYYY-MM-DD" /></el-form-item>
        <el-form-item label="End Date"><el-input v-model="draft.panel_end" placeholder="YYYY-MM-DD" /></el-form-item>
        <el-form-item label="Window Label"><el-input v-model="draft.panel_window_label" /></el-form-item>
      </div>
    </section>

    <section v-else class="setup-panel">
      <div class="review-actions">
        <el-button @click="previewSetup">Preview Datastream</el-button>
        <el-button type="primary" :disabled="!manualPreview || manualPreview.invalid > 0" @click="applyManual">Apply Datastream</el-button>
      </div>
      <PreviewTable v-if="manualPreview" :preview="manualPreview" />

      <div class="import-panel">
        <h3>Workbook Import</h3>
        <el-upload :show-file-list="false" :http-request="uploadWorkbook" accept=".xlsx">
          <el-button>Preview XLSX Workbook</el-button>
        </el-upload>
        <el-table v-if="importPreview" :data="importPreview.rows" stripe class="full-width" @selection-change="selectImportRows">
          <el-table-column type="selection" width="48" :selectable="isSelectableImportRow" />
          <el-table-column prop="row" label="Row" width="80" />
          <el-table-column prop="stream_id" label="Stream" />
          <el-table-column label="Status" width="110">
            <template #default="{ row }"><el-tag :type="row.valid ? 'success' : 'danger'">{{ row.valid ? "valid" : "error" }}</el-tag></template>
          </el-table-column>
          <el-table-column label="Errors">
            <template #default="{ row }">{{ row.errors?.join("; ") }}</template>
          </el-table-column>
        </el-table>
        <el-button v-if="importPreview" type="primary" :disabled="selectedImportSetups.length === 0" @click="applyImport">Apply Selected Rows</el-button>
      </div>
    </section>

    <div class="wizard-actions">
      <el-button :disabled="step === 0" @click="step -= 1">Back</el-button>
      <el-button v-if="step < 4" type="primary" @click="nextStep">Next</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, defineComponent, h, onMounted, reactive, ref } from "vue";
import { ElMessage, ElTable, ElTableColumn, ElTag } from "element-plus";
import type { UploadRequestOptions } from "element-plus/es/components/upload/src/upload";
import { api, getApiBase, getApiKey } from "../api/client";
import type { KioskLayoutOut, StreamSetupBatchIn, StreamSetupIn, StreamSetupPreviewOut, StreamSetupPreviewRow } from "../api/contracts";
import { buildSetupPayload, generatedStreamId, makeDraft, missingRequiredFields, validCanonicalRows } from "./datastreamSetup";

const step = ref(0);
const draft = reactive(makeDraft());
const manualPreview = ref<StreamSetupPreviewOut | null>(null);
const importPreview = ref<StreamSetupPreviewOut | null>(null);
const selectedImportRows = ref<StreamSetupPreviewRow[]>([]);
const kiosks = ref<KioskLayoutOut[]>([]);
const generatedId = computed(() => generatedStreamId(draft));
const defaultPriorBeta = computed(() => Number((draft.sigma ** 2).toFixed(6)));
const selectedImportSetups = computed(() => selectedImportRows.value.map((row) => row.canonical).filter(Boolean) as StreamSetupIn[]);

const PreviewTable = defineComponent({
  props: { preview: { type: Object, required: true } },
  setup(props) {
    return () =>
      h(ElTable, { data: (props.preview as StreamSetupPreviewOut).rows, stripe: true, class: "full-width" }, () => [
        h(ElTableColumn, { prop: "row", label: "Row", width: 80 }),
        h(ElTableColumn, { prop: "stream_id", label: "Stream" }),
        h(ElTableColumn, { label: "Status", width: 110 }, { default: ({ row }: { row: StreamSetupPreviewRow }) => h(ElTag, { type: row.valid ? "success" : "danger" }, () => (row.valid ? "valid" : "error")) }),
        h(ElTableColumn, { label: "Actions" }, { default: ({ row }: { row: StreamSetupPreviewRow }) => row.actions?.map((action) => `${action.entity}:${action.action}`).join(", ") }),
        h(ElTableColumn, { label: "Errors" }, { default: ({ row }: { row: StreamSetupPreviewRow }) => row.errors?.join("; ") }),
      ]);
  },
});

async function loadKiosks(): Promise<void> {
  const params = new URLSearchParams({ active: "true" });
  if (draft.site.trim()) {
    params.set("site", draft.site.trim());
  }
  if (draft.lab_bench.trim()) {
    params.set("lab_bench", draft.lab_bench.trim());
  }
  kiosks.value = await api.get<KioskLayoutOut[]>(`/kiosks?${params.toString()}`);
}

async function nextStep(): Promise<void> {
  const missing = step.value < 2 ? missingRequiredFields(draft) : [];
  if (missing.length) {
    ElMessage.error(`Missing: ${missing.join(", ")}`);
    return;
  }
  step.value += 1;
  if (step.value === 3) {
    await loadKiosks();
  }
}

async function previewSetup(): Promise<void> {
  try {
    manualPreview.value = await api.post<StreamSetupPreviewOut>("/stream-setups/preview", { rows: [buildSetupPayload(draft)] });
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "Preview failed");
  }
}

async function applyRows(rows: StreamSetupIn[]): Promise<void> {
  const payload: StreamSetupBatchIn = { rows };
  const result = await api.post<{ applied: number }>("/stream-setups/apply", payload);
  ElMessage.success(`Applied ${result.applied} datastream${result.applied === 1 ? "" : "s"}`);
  await loadKiosks();
}

async function applyManual(): Promise<void> {
  try {
    await applyRows([buildSetupPayload(draft)]);
    await previewSetup();
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "Apply failed");
  }
}

async function uploadWorkbook(options: UploadRequestOptions): Promise<void> {
  try {
    const formData = new FormData();
    formData.append("file", options.file);
    importPreview.value = await api.upload<StreamSetupPreviewOut>("/stream-setups/import/preview", formData);
    selectedImportRows.value = importPreview.value.rows.filter((row) => row.valid && row.canonical);
    options.onSuccess?.(importPreview.value);
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "Workbook preview failed");
  }
}

function selectImportRows(rows: StreamSetupPreviewRow[]): void {
  selectedImportRows.value = rows;
}

function isSelectableImportRow(row: StreamSetupPreviewRow): boolean {
  return Boolean(row.valid && row.canonical);
}

async function applyImport(): Promise<void> {
  try {
    await applyRows(selectedImportSetups.value);
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "Import apply failed");
  }
}

async function downloadTemplate(): Promise<void> {
  const response = await fetch(`${getApiBase()}/stream-setups/template.xlsx`, {
    headers: getApiKey() ? { "X-API-Key": getApiKey() as string } : {},
  });
  if (!response.ok) {
    ElMessage.error("Template download failed");
    return;
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "bayesianqc-datastream-template.xlsx";
  link.click();
  URL.revokeObjectURL(url);
}

onMounted(loadKiosks);
</script>

<style scoped>
.datastream-page { max-width: 1180px; }
.setup-steps { margin-bottom: 20px; }
.setup-panel { background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; padding: 18px; }
.form-grid { display: grid; gap: 14px; grid-template-columns: repeat(3, minmax(0, 1fr)); }
.kiosk-fields { margin-top: 14px; }
.review-actions, .wizard-actions { display: flex; gap: 10px; justify-content: flex-end; margin-top: 16px; }
.import-panel { border-top: 1px solid #e5e7eb; margin-top: 20px; padding-top: 16px; }
.import-panel h3 { font-size: 16px; margin: 0 0 12px; }
@media (max-width: 960px) {
  .form-grid { grid-template-columns: 1fr; }
}
</style>
