<template>
  <div class="page config-create-page">
    <div class="page-header">
      <div>
        <h2>{{ title }}</h2>
        <div class="muted">{{ subtitle }}</div>
      </div>
      <el-button @click="returnToBuilder">Cancel</el-button>
    </div>

    <section class="create-panel">
      <el-form label-position="top">
        <template v-if="kind === 'site'">
          <el-form-item label="Canonical Name"><el-input v-model="form.name" /></el-form-item>
          <el-form-item label="Code"><el-input v-model="form.code" /></el-form-item>
          <el-form-item label="Description"><el-input v-model="form.description" type="textarea" /></el-form-item>
        </template>

        <template v-else-if="kind === 'area'">
          <el-form-item label="Site">
            <el-select v-model="form.site_id" filterable class="full-width">
              <el-option v-for="site in sites" :key="site.id" :label="site.name" :value="site.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="Canonical Name"><el-input v-model="form.name" /></el-form-item>
          <el-form-item label="Description"><el-input v-model="form.description" type="textarea" /></el-form-item>
        </template>

        <template v-else-if="kind === 'instrument'">
          <el-form-item label="Site">
            <el-select v-model="form.site_id" filterable class="full-width" @change="onSiteChange">
              <el-option v-for="site in sites" :key="site.id" :label="site.name" :value="site.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="Area">
            <el-select v-model="form.lab_area_id" filterable class="full-width">
              <el-option v-for="area in areas" :key="area.id" :label="area.name" :value="area.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="Name"><el-input v-model="form.name" /></el-form-item>
          <el-form-item label="Manufacturer"><el-input v-model="form.manufacturer" /></el-form-item>
          <el-form-item label="Model"><el-input v-model="form.model" /></el-form-item>
        </template>

        <template v-else-if="kind === 'test'">
          <el-form-item label="Instrument">
            <el-select v-model="form.instrument_id" filterable class="full-width">
              <el-option v-for="instrument in instruments" :key="instrument.id" :label="instrumentLabel(instrument)" :value="instrument.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="Canonical Test / Method Name"><el-input v-model="form.name" /></el-form-item>
          <el-form-item label="Technique"><el-input v-model="form.technique" /></el-form-item>
          <el-form-item label="Description"><el-input v-model="form.description" type="textarea" /></el-form-item>
          <el-form-item label="Analyte Name"><el-input v-model="form.analyte_name" /></el-form-item>
          <el-form-item label="UOM"><el-input v-model="form.analyte_units" /></el-form-item>
          <el-form-item label="Result Resolution">
            <el-input-number v-model="form.analyte_result_resolution" class="full-width" :min="0.000001" :step="0.001" />
          </el-form-item>
          <el-form-item label="Analyte Description"><el-input v-model="form.analyte_description" type="textarea" /></el-form-item>
        </template>

        <template v-else-if="kind === 'analyte'">
          <el-form-item label="Test / Method">
            <el-select v-model="form.method_id" filterable class="full-width">
              <el-option v-for="method in methods" :key="method.id" :label="methodLabel(method)" :value="method.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="Name"><el-input v-model="form.name" /></el-form-item>
          <el-form-item label="UOM"><el-input v-model="form.units" /></el-form-item>
          <el-form-item label="Result Resolution">
            <el-input-number v-model="form.result_resolution" class="full-width" :min="0.000001" :step="0.001" />
          </el-form-item>
          <el-form-item label="Description"><el-input v-model="form.description" type="textarea" /></el-form-item>
        </template>

        <template v-else>
          <el-form-item label="Name"><el-input v-model="form.name" /></el-form-item>
          <el-form-item label="Manufacturer"><el-input v-model="form.manufacturer" /></el-form-item>
          <el-form-item label="Matrix"><el-input v-model="form.matrix" /></el-form-item>
          <el-form-item label="QC Level"><el-input v-model="form.qc_level" /></el-form-item>
          <el-form-item label="Lot"><el-input v-model="form.lot" /></el-form-item>
        </template>

        <el-form-item label="Active"><el-switch v-model="form.active" /></el-form-item>
      </el-form>
      <div class="create-actions">
        <el-button @click="returnToBuilder">Cancel</el-button>
        <el-button type="primary" :disabled="!canEditConfig" @click="save">Save</el-button>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { api } from "../api/client";
import type { AnalyteOut, ControlMaterialOut, EnterpriseSiteOut, InstrumentOut, LabAreaOut, MethodOut, TestCreateOut } from "../api/contracts";
import { canEditConfig } from "../api/session";
import { saveCreatedSelection } from "./datastreamSetup";
import { instrumentLabel, loadAreas, loadInstruments, loadMethods, loadSites, methodLabel, type ConfigCreateKind } from "./datastreamOptions";

type FormState = {
  active: boolean;
  site_id: number | null;
  lab_area_id: number | null;
  instrument_id: number | null;
  method_id: number | null;
  name: string;
  code: string;
  description: string;
  manufacturer: string;
  model: string;
  technique: string;
  analyte_name: string;
  analyte_units: string;
  analyte_result_resolution: number | null;
  analyte_description: string;
  units: string;
  result_resolution: number | null;
  matrix: string;
  qc_level: string;
  lot: string;
};

const route = useRoute();
const router = useRouter();
const sites = ref<EnterpriseSiteOut[]>([]);
const areas = ref<LabAreaOut[]>([]);
const instruments = ref<InstrumentOut[]>([]);
const methods = ref<MethodOut[]>([]);
const kind = computed(() => String(route.params.kind || "site") as ConfigCreateKind);
const draftKey = computed(() => String(route.query.draftKey || "default"));
const returnPath = computed(() => String(route.query.returnTo || "/config/datastreams"));
const labels: Record<ConfigCreateKind, string> = {
  site: "Site",
  area: "Area",
  instrument: "Instrument",
  test: "Test",
  analyte: "Analyte",
  material: "Control Material",
};
const title = computed(() => `Add ${labels[kind.value]}`);
const subtitle = computed(() => (kind.value === "test" ? "Method plus required analyte" : "Governed configuration"));

const form = reactive<FormState>({
  active: true,
  site_id: null,
  lab_area_id: null,
  instrument_id: null,
  method_id: null,
  name: "",
  code: "",
  description: "",
  manufacturer: "",
  model: "",
  technique: "",
  analyte_name: "",
  analyte_units: "",
  analyte_result_resolution: null,
  analyte_description: "",
  units: "",
  result_resolution: null,
  matrix: "",
  qc_level: "Level 1",
  lot: "",
});

async function loadSupport(): Promise<void> {
  sites.value = await loadSites();
  form.site_id = numberQuery("site_id") ?? form.site_id ?? (sites.value.length === 1 ? sites.value[0].id : null);
  areas.value = await loadAreas(form.site_id);
  form.lab_area_id = numberQuery("lab_area_id") ?? form.lab_area_id ?? (areas.value.length === 1 ? areas.value[0].id : null);
  instruments.value = await loadInstruments(form.site_id, form.lab_area_id);
  form.instrument_id = numberQuery("instrument_id") ?? form.instrument_id;
  methods.value = await loadMethods(form.instrument_id ?? null);
  form.method_id = numberQuery("method_id") ?? form.method_id;
}

function numberQuery(name: string): number | null {
  const value = route.query[name];
  const raw = Array.isArray(value) ? value[0] : value;
  const parsed = raw ? Number(raw) : NaN;
  return Number.isFinite(parsed) ? parsed : null;
}

async function onSiteChange(): Promise<void> {
  form.lab_area_id = null;
  areas.value = await loadAreas(form.site_id);
}

function optional(value: string): string | null {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function requireNumber(value: number | null, label: string): number {
  if (value === null) {
    throw new Error(`${label} is required`);
  }
  return value;
}

async function save(): Promise<void> {
  try {
    if (kind.value === "site") {
      const site = await api.post<EnterpriseSiteOut>("/enterprise-sites", { name: form.name, code: optional(form.code), description: optional(form.description), active: form.active });
      saveCreatedSelection(draftKey.value, { kind: "site", site_id: site.id });
    } else if (kind.value === "area") {
      const area = await api.post<LabAreaOut>("/lab-areas", { site_id: requireNumber(form.site_id, "Site"), name: form.name, description: optional(form.description), active: form.active });
      saveCreatedSelection(draftKey.value, { kind: "area", site_id: area.site_id, lab_area_id: area.id });
    } else if (kind.value === "instrument") {
      const instrument = await api.post<InstrumentOut>("/instruments", {
        site_id: form.site_id,
        lab_area_id: form.lab_area_id,
        name: form.name,
        manufacturer: optional(form.manufacturer),
        model: optional(form.model),
        active: form.active,
      });
      saveCreatedSelection(draftKey.value, { kind: "instrument", site_id: instrument.site_id ?? null, lab_area_id: instrument.lab_area_id ?? null, instrument_id: instrument.id });
    } else if (kind.value === "test") {
      const test = await api.post<TestCreateOut>("/tests", {
        instrument_id: requireNumber(form.instrument_id, "Instrument"),
        name: form.name,
        technique: optional(form.technique),
        description: optional(form.description),
        analyte_name: form.analyte_name,
        analyte_units: form.analyte_units,
        analyte_result_resolution: requireNumber(form.analyte_result_resolution, "Result resolution"),
        analyte_description: optional(form.analyte_description),
        active: form.active,
      });
      saveCreatedSelection(draftKey.value, { kind: "test", instrument_id: test.method.instrument_id, method_id: test.method.id, analyte_id: test.analyte.id });
    } else if (kind.value === "analyte") {
      const analyte = await api.post<AnalyteOut>("/analytes", {
        method_id: requireNumber(form.method_id, "Method"),
        name: form.name,
        units: form.units,
        result_resolution: requireNumber(form.result_resolution, "Result resolution"),
        description: optional(form.description),
        active: form.active,
      });
      saveCreatedSelection(draftKey.value, { kind: "analyte", method_id: analyte.method_id, analyte_id: analyte.id });
    } else {
      const material = await api.post<ControlMaterialOut>("/control-materials", {
        name: form.name,
        manufacturer: optional(form.manufacturer),
        matrix: optional(form.matrix),
        qc_level: form.qc_level,
        lot: form.lot,
        active: form.active,
      });
      saveCreatedSelection(draftKey.value, { kind: "material", control_material_id: material.id });
    }
    ElMessage.success("Saved");
    await returnToBuilder();
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "Save failed");
  }
}

async function returnToBuilder(): Promise<void> {
  await router.push(returnPath.value);
}

onMounted(loadSupport);
</script>

<style scoped>
.config-create-page { max-width: 760px; }
.create-panel { background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; padding: 18px; }
.create-actions { display: flex; gap: 10px; justify-content: flex-end; margin-top: 16px; }
</style>
