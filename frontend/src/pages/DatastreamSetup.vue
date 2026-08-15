<template>
  <div class="page datastream-page">
    <div class="page-header">
      <div>
        <h2>Add Datastream</h2>
        <div class="muted">Select governed config, preview the stream, then apply atomically.</div>
      </div>
      <el-button @click="downloadTemplate">Download XLSX Template</el-button>
    </div>

    <section class="setup-panel">
      <h3>Core Configuration</h3>
      <div class="form-grid">
        <el-form-item label="Enterprise Site"><SelectAction><el-select v-model="draft.site_id" filterable clearable class="full-width" @change="onSiteChange"><el-option v-for="site in sites" :key="site.id" :label="site.name" :value="site.id" /></el-select><el-button v-if="canEditConfig" @click="goAdd('site')">Add new</el-button></SelectAction></el-form-item>
        <el-form-item label="Lab Bench / Area"><SelectAction><el-select v-model="draft.lab_area_id" filterable clearable class="full-width" :disabled="!draft.site_id" @change="onAreaChange"><el-option v-for="area in areas" :key="area.id" :label="area.name" :value="area.id" /></el-select><el-button v-if="canEditConfig" :disabled="!draft.site_id" @click="goAdd('area')">Add new</el-button></SelectAction></el-form-item>
        <el-form-item label="Instrument"><SelectAction><el-select v-model="draft.instrument_id" filterable clearable class="full-width" :disabled="!draft.lab_area_id" @change="onInstrumentChange"><el-option v-for="instrument in instruments" :key="instrument.id" :label="instrumentLabel(instrument)" :value="instrument.id" /></el-select><el-button v-if="canEditConfig" :disabled="!draft.lab_area_id" @click="goAdd('instrument')">Add new</el-button></SelectAction></el-form-item>
        <el-form-item label="Test / Method"><SelectAction><el-select v-model="draft.method_id" filterable clearable class="full-width" :disabled="!draft.instrument_id" @change="onMethodChange"><el-option v-for="method in methods" :key="method.id" :label="methodLabel(method)" :value="method.id" /></el-select><el-button v-if="canEditConfig" :disabled="!draft.instrument_id" @click="goAdd('test')">Add new</el-button></SelectAction></el-form-item>
        <el-form-item label="Analyte"><SelectAction><el-select v-model="draft.analyte_id" filterable clearable class="full-width" :disabled="!draft.method_id" @change="onAnalyteChange"><el-option v-for="analyte in analytes" :key="analyte.id" :label="analyteLabel(analyte)" :value="analyte.id" /></el-select><el-button v-if="canEditConfig" :disabled="!draft.method_id" @click="goAdd('analyte')">Add new</el-button></SelectAction></el-form-item>
        <el-form-item label="Control Material"><SelectAction><el-select v-model="draft.control_material_id" filterable clearable class="full-width" @change="onMaterialChange"><el-option v-for="material in materials" :key="material.id" :label="materialLabel(material)" :value="material.id" /></el-select><el-button v-if="canEditConfig" @click="goAdd('material')">Add new</el-button></SelectAction></el-form-item>
      </div>
      <el-form-item label="Stream ID"><el-input v-model="draft.stream_id" :placeholder="generatedId" /></el-form-item>
    </section>

    <section class="setup-panel">
      <h3>Limits / Prior</h3>
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
      <el-form-item label="Version Reason"><el-input v-model="draft.config_reason" /></el-form-item>
    </section>

    <section class="setup-panel">
      <h3>Kiosk</h3>
      <el-checkbox v-model="draft.kiosk_enabled">Assign this datastream to a saved kiosk</el-checkbox>
      <div v-if="draft.kiosk_enabled" class="form-grid kiosk-fields">
        <el-form-item label="Kiosk"><el-select v-model="draft.kiosk_slug" filterable clearable class="full-width"><el-option v-for="kiosk in kiosks" :key="kiosk.slug" :label="kiosk.label" :value="kiosk.slug" /></el-select></el-form-item>
        <el-form-item label="Panel Title"><el-input v-model="draft.panel_title" :placeholder="`${draft.parameter_name} - ${draft.instrument_name}`" /></el-form-item>
        <el-form-item label="Start Date"><el-input v-model="draft.panel_start" placeholder="YYYY-MM-DD" /></el-form-item>
        <el-form-item label="End Date"><el-input v-model="draft.panel_end" placeholder="YYYY-MM-DD" /></el-form-item>
        <el-form-item label="Window Label"><el-input v-model="draft.panel_window_label" /></el-form-item>
      </div>
    </section>

    <section class="setup-panel">
      <div class="review-actions">
        <el-button @click="previewSetup">Preview Datastream</el-button>
        <el-button type="primary" :disabled="!manualPreview || manualPreview.invalid > 0" @click="applyManual">Apply Datastream</el-button>
      </div>
      <DatastreamPreviewTable v-if="manualPreview" :preview="manualPreview" />

      <div class="import-panel">
        <h3>Workbook Import</h3>
        <el-upload :show-file-list="false" :http-request="uploadWorkbook" accept=".xlsx">
          <el-button>Preview XLSX Workbook</el-button>
        </el-upload>
        <el-table v-if="importPreview" :data="importPreview.rows" stripe class="full-width" @selection-change="selectImportRows">
          <el-table-column type="selection" width="48" :selectable="isSelectableImportRow" />
          <el-table-column prop="row" label="Row" width="80" />
          <el-table-column prop="stream_id" label="Stream" />
          <el-table-column label="Status" width="110"><template #default="{ row }"><el-tag :type="row.valid ? 'success' : 'danger'">{{ row.valid ? "valid" : "error" }}</el-tag></template></el-table-column>
          <el-table-column label="Errors"><template #default="{ row }">{{ row.errors?.join("; ") }}</template></el-table-column>
        </el-table>
        <el-button v-if="importPreview" type="primary" :disabled="selectedImportSetups.length === 0" @click="applyImport">Apply Selected Rows</el-button>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, defineComponent, h, onMounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import type { UploadRequestOptions } from "element-plus/es/components/upload/src/upload";
import { api, getApiBase, getApiKey } from "../api/client";
import type { AnalyteOut, ControlMaterialOut, EnterpriseSiteOut, InstrumentOut, KioskLayoutOut, LabAreaOut, MethodOut, StreamSetupBatchIn, StreamSetupIn, StreamSetupPreviewOut, StreamSetupPreviewRow } from "../api/contracts";
import { canEditConfig } from "../api/session";
import DatastreamPreviewTable from "./DatastreamPreviewTable.vue";
import { buildSetupPayload, consumeCreatedSelection, generatedStreamId, loadDatastreamDraft, makeDraft, missingRequiredFields, saveDatastreamDraft, type CreatedSelection } from "./datastreamSetup";
import { analyteLabel, instrumentLabel, loadAnalytes, loadAreas, loadInstruments, loadKiosks, loadMaterials, loadMethods, loadSites, materialLabel, methodLabel, type ConfigCreateKind } from "./datastreamOptions";

const SelectAction = defineComponent({ setup(_, { slots }) { return () => h("div", { class: "select-action" }, slots.default?.()); } });
const route = useRoute();
const router = useRouter();
const draftKey = "default";
const draft = reactive(makeDraft());
const sites = ref<EnterpriseSiteOut[]>([]);
const areas = ref<LabAreaOut[]>([]);
const instruments = ref<InstrumentOut[]>([]);
const methods = ref<MethodOut[]>([]);
const analytes = ref<AnalyteOut[]>([]);
const materials = ref<ControlMaterialOut[]>([]);
const kiosks = ref<KioskLayoutOut[]>([]);
const manualPreview = ref<StreamSetupPreviewOut | null>(null);
const importPreview = ref<StreamSetupPreviewOut | null>(null);
const selectedImportRows = ref<StreamSetupPreviewRow[]>([]);
const generatedId = computed(() => generatedStreamId(draft));
const defaultPriorBeta = computed(() => Number((draft.sigma ** 2).toFixed(6)));
const selectedImportSetups = computed(() => selectedImportRows.value.map((row) => row.canonical).filter(Boolean) as StreamSetupIn[]);

watch(draft, () => { manualPreview.value = null; }, { deep: true });

function clearFromArea(): void { draft.instrument_id = null; draft.instrument_name = ""; clearFromInstrument(); }
function clearFromInstrument(): void { draft.method_id = null; draft.method_name = ""; draft.method_technique = ""; clearFromMethod(); }
function clearFromMethod(): void { draft.analyte_id = null; draft.parameter_name = ""; draft.units = ""; }

function syncSite(): void {
  const site = sites.value.find((row) => row.id === draft.site_id);
  draft.site = site?.name ?? "";
}

function syncArea(): void {
  const area = areas.value.find((row) => row.id === draft.lab_area_id);
  draft.lab_bench = area?.name ?? "";
}

function syncInstrument(): void {
  const row = instruments.value.find((item) => item.id === draft.instrument_id);
  draft.instrument_name = row?.name ?? "";
  draft.instrument_manufacturer = row?.manufacturer ?? "";
  draft.instrument_model = row?.model ?? "";
}

function syncMethod(): void {
  const row = methods.value.find((item) => item.id === draft.method_id);
  draft.method_name = row?.name ?? "";
  draft.method_technique = row?.technique ?? "";
}

function syncAnalyte(): void {
  const row = analytes.value.find((item) => item.id === draft.analyte_id);
  draft.parameter_name = row?.name ?? "";
  draft.units = row?.units ?? "";
}

function syncMaterial(): void {
  const row = materials.value.find((item) => item.id === draft.control_material_id);
  draft.material_name = row?.name ?? "";
  draft.material_manufacturer = row?.manufacturer ?? "";
  draft.matrix = row?.matrix ?? "";
  draft.qc_level = row?.qc_level ?? draft.qc_level;
  draft.control_material_lot = row?.lot ?? "";
}

function applyCreatedSelection(selection: CreatedSelection | null): void {
  if (!selection) return;
  if ("site_id" in selection) draft.site_id = selection.site_id;
  if ("lab_area_id" in selection) draft.lab_area_id = selection.lab_area_id;
  if ("instrument_id" in selection) draft.instrument_id = selection.instrument_id;
  if ("method_id" in selection) draft.method_id = selection.method_id;
  if ("analyte_id" in selection) draft.analyte_id = selection.analyte_id;
  if ("control_material_id" in selection) draft.control_material_id = selection.control_material_id;
}

async function refreshCascade(): Promise<void> {
  sites.value = await loadSites();
  if (!draft.site_id && sites.value.length === 1) draft.site_id = sites.value[0].id;
  if (draft.site_id && !sites.value.some((row) => row.id === draft.site_id)) draft.site_id = null;
  syncSite();
  areas.value = draft.site_id ? await loadAreas(draft.site_id) : [];
  if (draft.lab_area_id && !areas.value.some((row) => row.id === draft.lab_area_id)) { draft.lab_area_id = null; clearFromArea(); }
  if (!draft.lab_area_id && areas.value.length === 1) draft.lab_area_id = areas.value[0].id;
  syncArea();
  instruments.value = await loadInstruments(draft.site_id, draft.lab_area_id);
  if (draft.instrument_id && !instruments.value.some((row) => row.id === draft.instrument_id)) { draft.instrument_id = null; clearFromInstrument(); }
  syncInstrument();
  methods.value = draft.instrument_id ? await loadMethods(draft.instrument_id) : [];
  if (draft.method_id && !methods.value.some((row) => row.id === draft.method_id)) { draft.method_id = null; clearFromMethod(); }
  syncMethod();
  analytes.value = draft.method_id ? await loadAnalytes(draft.method_id) : [];
  if (draft.analyte_id && !analytes.value.some((row) => row.id === draft.analyte_id)) draft.analyte_id = null;
  syncAnalyte();
  materials.value = await loadMaterials();
  if (draft.control_material_id && !materials.value.some((row) => row.id === draft.control_material_id)) draft.control_material_id = null;
  syncMaterial();
  kiosks.value = await loadKiosks(draft.site, draft.lab_bench);
}

async function onSiteChange(): Promise<void> { syncSite(); draft.lab_area_id = null; draft.lab_bench = ""; clearFromArea(); await refreshCascade(); }
async function onAreaChange(): Promise<void> { syncArea(); clearFromArea(); await refreshCascade(); }
async function onInstrumentChange(): Promise<void> { syncInstrument(); clearFromInstrument(); await refreshCascade(); }
async function onMethodChange(): Promise<void> { syncMethod(); clearFromMethod(); await refreshCascade(); }
function onAnalyteChange(): void { syncAnalyte(); }
function onMaterialChange(): void { syncMaterial(); }

async function goAdd(kind: ConfigCreateKind): Promise<void> {
  saveDatastreamDraft(draftKey, draft);
  const query: Record<string, string> = { returnTo: route.fullPath, draftKey };
  if (draft.site_id) query.site_id = String(draft.site_id);
  if (draft.lab_area_id) query.lab_area_id = String(draft.lab_area_id);
  if (draft.instrument_id) query.instrument_id = String(draft.instrument_id);
  if (draft.method_id) query.method_id = String(draft.method_id);
  await router.push({ path: `/config/create/${kind}`, query });
}

async function previewSetup(): Promise<void> {
  const missing = missingRequiredFields(draft);
  if (missing.length) { ElMessage.error(`Missing: ${missing.join(", ")}`); return; }
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
  await refreshCascade();
}

async function applyManual(): Promise<void> {
  try { await applyRows([buildSetupPayload(draft)]); await previewSetup(); } catch (error) { ElMessage.error(error instanceof Error ? error.message : "Apply failed"); }
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

function selectImportRows(rows: StreamSetupPreviewRow[]): void { selectedImportRows.value = rows; }
function isSelectableImportRow(row: StreamSetupPreviewRow): boolean { return Boolean(row.valid && row.canonical); }
async function applyImport(): Promise<void> { try { await applyRows(selectedImportSetups.value); } catch (error) { ElMessage.error(error instanceof Error ? error.message : "Import apply failed"); } }

async function downloadTemplate(): Promise<void> {
  const response = await fetch(`${getApiBase()}/stream-setups/template.xlsx`, { headers: getApiKey() ? { "X-API-Key": getApiKey() as string } : {} });
  if (!response.ok) { ElMessage.error("Template download failed"); return; }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "bayesianqc-datastream-template.xlsx";
  link.click();
  URL.revokeObjectURL(url);
}

onMounted(async () => {
  Object.assign(draft, loadDatastreamDraft(draftKey) ?? {});
  applyCreatedSelection(consumeCreatedSelection(draftKey));
  await refreshCascade();
});
</script>

<style scoped>
.datastream-page { max-width: 1180px; }
.setup-panel { background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; margin-bottom: 16px; padding: 18px; }
.setup-panel h3 { font-size: 16px; margin: 0 0 12px; }
.form-grid { display: grid; gap: 14px; grid-template-columns: repeat(3, minmax(0, 1fr)); }
.select-action { align-items: center; display: flex; gap: 8px; width: 100%; }
.kiosk-fields { margin-top: 14px; }
.review-actions { display: flex; gap: 10px; justify-content: flex-end; margin-bottom: 16px; }
.import-panel { border-top: 1px solid #e5e7eb; margin-top: 20px; padding-top: 16px; }
.import-panel h3 { font-size: 16px; margin: 0 0 12px; }
@media (max-width: 960px) {
  .form-grid { grid-template-columns: 1fr; }
  .select-action { align-items: stretch; flex-direction: column; }
}
</style>
