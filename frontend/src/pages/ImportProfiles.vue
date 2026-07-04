<template>
  <div class="page import-profile-page">
    <div class="page-header">
      <div>
        <h2>Parser Profiles</h2>
        <div class="muted">Versioned parser configuration for instrument result and artifact files.</div>
      </div>
      <div class="toolbar">
        <el-select v-model="statusFilter" class="status-filter" @change="loadProfiles">
          <el-option label="All" value="" />
          <el-option label="Active" value="active" />
          <el-option label="Draft" value="draft" />
        </el-select>
        <el-button @click="loadProfiles">Refresh</el-button>
      </div>
    </div>

    <div class="profile-layout">
      <section class="setup-panel">
        <div class="section-title">{{ editing ? "New Version" : "New Profile" }}</div>
        <el-form label-position="top">
          <div class="form-grid">
            <el-form-item label="Name"><el-input v-model="draft.name" /></el-form-item>
            <el-form-item label="Type">
              <el-select v-model="draft.profile_type" class="full-width">
                <el-option label="delimited_direct" value="delimited_direct" />
                <el-option label="instrument_table_discovery" value="instrument_table_discovery" />
                <el-option label="xml_mapping" value="xml_mapping" />
              </el-select>
            </el-form-item>
            <el-form-item label="Status">
              <el-select v-model="draft.status" class="full-width">
                <el-option label="draft" value="draft" />
                <el-option label="active" value="active" />
              </el-select>
            </el-form-item>
            <el-form-item label="Source ID"><el-input v-model="draft.source_id" /></el-form-item>
            <el-form-item label="Instrument"><el-input v-model="draft.instrument" /></el-form-item>
            <el-form-item label="Signature"><el-input v-model="draft.signature" /></el-form-item>
          </div>
          <el-form-item label="File Extensions">
            <el-input v-model="extensionText" placeholder=".csv, .txt, .dat" />
          </el-form-item>
          <el-form-item label="Filename Patterns">
            <el-input v-model="patternText" placeholder="*.csv, QC_*" />
          </el-form-item>
          <el-form-item label="Config JSON">
            <el-input v-model="configText" type="textarea" :rows="14" />
          </el-form-item>
          <el-form-item v-if="editing" label="Reason">
            <el-input v-model="reason" />
          </el-form-item>
          <div class="toolbar end">
            <el-button @click="resetDraft">Clear</el-button>
            <el-button type="primary" :disabled="!canManageImports" @click="saveProfile">
              {{ editing ? "Save Version" : "Create Profile" }}
            </el-button>
          </div>
        </el-form>
      </section>

      <el-table v-loading="loading" :data="profiles" stripe class="full-width">
        <el-table-column label="Profile" min-width="230">
          <template #default="{ row }">
            <strong>{{ row.name }}</strong>
            <div class="small-text muted">v{{ row.version }} · {{ row.profile_type }}</div>
          </template>
        </el-table-column>
        <el-table-column label="Status" width="100">
          <template #default="{ row }"><el-tag :type="row.status === 'active' ? 'success' : 'info'">{{ row.status }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="source_id" label="Source" width="130" />
        <el-table-column prop="instrument" label="Instrument" width="160" />
        <el-table-column label="Files" min-width="180">
          <template #default="{ row }">
            <div>{{ row.file_extensions.join(", ") || "any extension" }}</div>
            <div class="small-text muted">{{ row.filename_patterns.join(", ") || "no filename pattern" }}</div>
          </template>
        </el-table-column>
        <el-table-column label="Actions" width="120">
          <template #default="{ row }">
            <el-button size="small" @click="editProfile(row)">Edit</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { api } from "../api/client";
import type { ParserProfileIn, ParserProfileOut, ParserProfileStatus, ParserProfileType, ParserProfileUpdate } from "../api/contracts";
import { canManageImports } from "../api/session";

type Draft = {
  name: string;
  profile_type: ParserProfileType;
  status: ParserProfileStatus;
  source_id: string;
  instrument: string;
  signature: string;
};

const profiles = ref<ParserProfileOut[]>([]);
const loading = ref(false);
const statusFilter = ref<ParserProfileStatus | "">("active");
const extensionText = ref(".csv");
const patternText = ref("*.csv");
const configText = ref(JSON.stringify({
  delimiter: ",",
  columns: {
    timestamp: "Timestamp",
    result_value: "Result",
    analyte: "Analyte",
    qc_level: "Level",
    instrument_id: "Instrument",
    method_id: "Method",
    control_material_lot: "Lot",
    units: "Units",
  },
  defaults: {},
  matching_window_hours: 3,
  auto_apply_ready_rows: false,
}, null, 2));
const reason = ref("");
const editing = ref<ParserProfileOut | null>(null);
const draft = reactive<Draft>({
  name: "",
  profile_type: "delimited_direct",
  status: "draft",
  source_id: "",
  instrument: "",
  signature: "",
});

function splitList(value: string): string[] {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

function nullable(value: string): string | null {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function parseConfig(): ParserProfileIn["config"] {
  try {
    return JSON.parse(configText.value) as ParserProfileIn["config"];
  } catch {
    throw new Error("Config JSON is invalid");
  }
}

function buildCreatePayload(): ParserProfileIn {
  return {
    name: draft.name.trim(),
    profile_type: draft.profile_type,
    status: draft.status,
    source_id: nullable(draft.source_id),
    instrument: nullable(draft.instrument),
    signature: nullable(draft.signature),
    file_extensions: splitList(extensionText.value),
    filename_patterns: splitList(patternText.value),
    config: parseConfig(),
  };
}

async function loadProfiles(): Promise<void> {
  loading.value = true;
  try {
    const query = statusFilter.value ? `?status=${statusFilter.value}` : "";
    profiles.value = await api.get<ParserProfileOut[]>(`/qc/import-profiles${query}`);
  } finally {
    loading.value = false;
  }
}

function resetDraft(): void {
  editing.value = null;
  draft.name = "";
  draft.profile_type = "delimited_direct";
  draft.status = "draft";
  draft.source_id = "";
  draft.instrument = "";
  draft.signature = "";
  extensionText.value = ".csv";
  patternText.value = "*.csv";
  reason.value = "";
}

function editProfile(profile: ParserProfileOut): void {
  editing.value = profile;
  draft.name = profile.name;
  draft.profile_type = profile.profile_type;
  draft.status = profile.status;
  draft.source_id = profile.source_id ?? "";
  draft.instrument = profile.instrument ?? "";
  draft.signature = profile.signature ?? "";
  extensionText.value = (profile.file_extensions ?? []).join(", ");
  patternText.value = (profile.filename_patterns ?? []).join(", ");
  configText.value = JSON.stringify(profile.config, null, 2);
}

async function saveProfile(): Promise<void> {
  try {
    if (editing.value) {
      const payload: ParserProfileUpdate = { ...buildCreatePayload(), reason: nullable(reason.value) };
      await api.patch<ParserProfileOut>(`/qc/import-profiles/${editing.value.id}`, payload);
      ElMessage.success("Parser profile version saved");
    } else {
      await api.post<ParserProfileOut>("/qc/import-profiles", buildCreatePayload());
      ElMessage.success("Parser profile created");
    }
    resetDraft();
    await loadProfiles();
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "Profile save failed");
  }
}

onMounted(loadProfiles);
</script>

<style scoped>
.import-profile-page { max-width: 1320px; }
.profile-layout { display: grid; gap: 16px; grid-template-columns: minmax(360px, 0.95fr) minmax(0, 1.4fr); }
.setup-panel { background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; padding: 16px; }
.section-title { font-size: 16px; font-weight: 700; margin-bottom: 12px; }
.form-grid { display: grid; gap: 12px; grid-template-columns: repeat(2, minmax(0, 1fr)); }
.status-filter { width: 130px; }
.end { justify-content: flex-end; }
@media (max-width: 1100px) {
  .profile-layout { grid-template-columns: 1fr; }
  .form-grid { grid-template-columns: 1fr; }
}
</style>
