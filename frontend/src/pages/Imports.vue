<template>
  <div class="page imports-page">
    <div class="page-header">
      <div>
        <h2>Import Batches</h2>
        <div class="muted">Instrument file previews, row exceptions, artifacts, and apply history.</div>
      </div>
      <div class="toolbar">
        <el-select v-model="statusFilter" class="status-filter" @change="loadBatches">
          <el-option label="All" value="" />
          <el-option label="Ready" value="ready_to_apply" />
          <el-option label="Exceptions" value="parsed_with_exceptions" />
          <el-option label="Failed" value="failed_to_ingest" />
          <el-option label="Applied" value="applied" />
        </el-select>
        <el-button @click="loadBatches">Refresh</el-button>
      </div>
    </div>

    <section class="setup-panel">
      <div class="upload-grid">
        <el-select v-model="uploadProfileId" filterable clearable placeholder="Auto-select profile" class="full-width">
          <el-option v-for="profile in profiles" :key="profile.id" :label="`${profile.name} v${profile.version}`" :value="profile.id" />
        </el-select>
        <el-input v-model="sourceId" placeholder="Source ID" />
        <el-input v-model="sourcePath" placeholder="Source path" />
        <el-checkbox v-model="autoApply">Auto-apply ready rows</el-checkbox>
        <el-upload :show-file-list="false" :http-request="uploadFile">
          <el-button type="primary" :disabled="!canIngestQc">Upload File</el-button>
        </el-upload>
      </div>
    </section>

    <div class="batch-layout">
      <el-table v-loading="loading" :data="batches" stripe class="full-width" highlight-current-row @row-click="selectBatch">
        <el-table-column label="File" min-width="220">
          <template #default="{ row }">
            <strong>{{ row.filename }}</strong>
            <div class="small-text muted">{{ row.file_hash.slice(0, 16) }} · {{ formatDate(row.received_at) }}</div>
          </template>
        </el-table-column>
        <el-table-column label="Status" width="150">
          <template #default="{ row }">
            <el-tag :type="statusTag(row.status)">{{ row.status }}</el-tag>
            <div class="small-text muted">{{ row.collector_action }}</div>
          </template>
        </el-table-column>
        <el-table-column label="Rows" width="150">
          <template #default="{ row }">
            <div>{{ row.ready_rows }} ready</div>
            <div class="small-text muted">{{ row.exception_rows }} exceptions · {{ row.applied_rows }} applied</div>
          </template>
        </el-table-column>
      </el-table>

      <section class="setup-panel detail-panel">
        <template v-if="detail">
          <div class="detail-header">
            <div>
              <h3>{{ detail.filename }}</h3>
              <div class="muted small-text">{{ detail.archived_path }}</div>
            </div>
            <el-button type="primary" :disabled="!canIngestQc || detail.ready_rows === 0" @click="applyBatch">Apply Ready Rows</el-button>
          </div>
          <div class="count-strip">
            <el-tag>{{ detail.total_rows }} rows</el-tag>
            <el-tag type="success">{{ detail.ready_rows }} ready</el-tag>
            <el-tag type="warning">{{ detail.exception_rows }} exceptions</el-tag>
            <el-tag type="info">{{ detail.artifact_count }} artifacts</el-tag>
          </div>
          <el-alert v-if="detail.failure_reason" :title="detail.failure_reason" type="error" show-icon :closable="false" />

          <el-tabs>
            <el-tab-pane label="Rows">
              <el-table :data="detail.rows" stripe class="full-width">
                <el-table-column type="expand">
                  <template #default="{ row }">
                    <div class="row-detail">
                      <pre>{{ pretty(row.raw) }}</pre>
                      <pre>{{ pretty(row.parsed_fields) }}</pre>
                    </div>
                  </template>
                </el-table-column>
                <el-table-column prop="row_number" label="Row" width="70" />
                <el-table-column prop="row_type" label="Type" width="110" />
                <el-table-column label="Status" width="150">
                  <template #default="{ row }"><el-tag :type="rowTag(row.status)">{{ row.status }}</el-tag></template>
                </el-table-column>
                <el-table-column label="Stream" min-width="180">
                  <template #default="{ row }">{{ row.stream_id || row.parsed_fields.stream_id || "unmapped" }}</template>
                </el-table-column>
                <el-table-column label="Issues" min-width="230">
                  <template #default="{ row }">{{ [...row.errors, ...row.warnings].join("; ") }}</template>
                </el-table-column>
                <el-table-column label="Resolve" min-width="340">
                  <template #default="{ row }">
                    <div v-if="canIngestQc && row.status !== 'applied'" class="resolve-controls">
                      <el-select :model-value="rowEdit(row.id).stream_id" filterable clearable placeholder="Stream" @update:model-value="setRowStream(row.id, $event)">
                        <el-option v-for="stream in streams" :key="stream.stream_id" :label="stream.stream_id" :value="stream.stream_id" />
                      </el-select>
                      <el-select :model-value="rowEdit(row.id).backlog_id" filterable clearable placeholder="Backlog" @update:model-value="setRowBacklog(row.id, $event)">
                        <el-option v-for="item in backlog" :key="item.id" :label="`${item.id} · ${item.analyte} ${item.qc_level}`" :value="item.id" />
                      </el-select>
                      <el-button size="small" @click="saveRow(row.id)">Save</el-button>
                    </div>
                  </template>
                </el-table-column>
              </el-table>
            </el-tab-pane>
            <el-tab-pane label="Artifacts">
              <el-table :data="detail.artifacts" stripe class="full-width">
                <el-table-column prop="role" label="Role" width="180" />
                <el-table-column prop="filename" label="File" />
                <el-table-column prop="archived_path" label="Archive" />
              </el-table>
            </el-tab-pane>
            <el-tab-pane label="Peaks">
              <el-table :data="detail.peaks" stripe class="full-width">
                <el-table-column prop="analyte" label="Analyte" />
                <el-table-column prop="peak_name" label="Peak" />
                <el-table-column prop="retention_time" label="RT" />
                <el-table-column prop="area" label="Area" />
                <el-table-column prop="height" label="Height" />
              </el-table>
            </el-tab-pane>
          </el-tabs>
        </template>
        <div v-else class="muted">Select an import batch to review rows and artifacts.</div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import type { UploadRequestOptions } from "element-plus/es/components/upload/src/upload";
import { api } from "../api/client";
import type {
  ImportBatchDetailOut,
  ImportBatchOut,
  ImportBatchStatus,
  ImportCreateOut,
  ImportRowStatus,
  ImportRowUpdate,
  ParserProfileOut,
  QCBacklogItemOut,
  StreamConfigOut,
} from "../api/contracts";
import { canIngestQc } from "../api/session";

type RowEdit = { stream_id: string; backlog_id: number | null };

const batches = ref<ImportBatchOut[]>([]);
const detail = ref<ImportBatchDetailOut | null>(null);
const profiles = ref<ParserProfileOut[]>([]);
const streams = ref<StreamConfigOut[]>([]);
const backlog = ref<QCBacklogItemOut[]>([]);
const loading = ref(false);
const statusFilter = ref<ImportBatchStatus | "">("");
const uploadProfileId = ref<number | null>(null);
const sourceId = ref("");
const sourcePath = ref("");
const autoApply = ref(false);
const edits = reactive<Record<number, RowEdit>>({});

function formatDate(value: string): string {
  return new Date(value).toLocaleString();
}

function pretty(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

function statusTag(status: ImportBatchStatus): "success" | "warning" | "danger" | "info" {
  if (status === "applied") return "success";
  if (status === "failed_to_ingest") return "danger";
  if (status === "ready_to_apply") return "warning";
  return "info";
}

function rowTag(status: ImportRowStatus): "success" | "warning" | "danger" | "info" {
  if (status === "applied") return "success";
  if (status === "parse_error" || status === "quarantined") return "danger";
  if (status === "needs_review" || status === "ready_to_apply") return "warning";
  return "info";
}

function rowEdit(rowId: number): RowEdit {
  edits[rowId] ??= { stream_id: "", backlog_id: null };
  return edits[rowId];
}

function setRowStream(rowId: number, value: string): void {
  rowEdit(rowId).stream_id = value || "";
}

function setRowBacklog(rowId: number, value: number | ""): void {
  rowEdit(rowId).backlog_id = value === "" ? null : Number(value);
}

async function loadProfiles(): Promise<void> {
  profiles.value = await api.get<ParserProfileOut[]>("/qc/import-profiles?status=active");
}

async function loadReferenceData(): Promise<void> {
  const [streamRows, backlogRows] = await Promise.all([
    api.get<StreamConfigOut[]>("/streams"),
    api.get<QCBacklogItemOut[]>("/qc/backlog?status=open&status=in_progress"),
  ]);
  streams.value = streamRows;
  backlog.value = backlogRows;
}

async function loadBatches(): Promise<void> {
  loading.value = true;
  try {
    const query = statusFilter.value ? `?status=${statusFilter.value}` : "";
    batches.value = await api.get<ImportBatchOut[]>(`/qc/imports${query}`);
  } finally {
    loading.value = false;
  }
}

async function selectBatch(row: ImportBatchOut): Promise<void> {
  detail.value = await api.get<ImportBatchDetailOut>(`/qc/imports/${row.id}`);
}

async function uploadFile(options: UploadRequestOptions): Promise<void> {
  try {
    const form = new FormData();
    form.append("file", options.file);
    if (uploadProfileId.value) form.append("profile_id", String(uploadProfileId.value));
    if (sourceId.value.trim()) form.append("source_id", sourceId.value.trim());
    if (sourcePath.value.trim()) form.append("source_path", sourcePath.value.trim());
    form.append("auto_apply", String(autoApply.value));
    const created = await api.upload<ImportCreateOut>("/qc/imports", form);
    detail.value = created.batch;
    ElMessage.success(`Import ${created.batch.status}; collector action ${created.collector_action}`);
    await loadBatches();
    options.onSuccess?.(created);
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "Import upload failed");
  }
}

async function saveRow(rowId: number): Promise<void> {
  const edit = rowEdit(rowId);
  const payload: ImportRowUpdate = {
    stream_id: edit.stream_id || null,
    qc_backlog_item_id: edit.backlog_id,
    reason: "manual import row association",
  };
  await api.patch(`/qc/imports/rows/${rowId}`, payload);
  if (detail.value) detail.value = await api.get<ImportBatchDetailOut>(`/qc/imports/${detail.value.id}`);
  ElMessage.success("Import row updated");
}

async function applyBatch(): Promise<void> {
  if (!detail.value) return;
  detail.value = await api.post<ImportBatchDetailOut>(`/qc/imports/${detail.value.id}/apply`);
  await loadBatches();
  ElMessage.success("Ready rows applied");
}

onMounted(async () => {
  await Promise.all([loadProfiles(), loadReferenceData(), loadBatches()]);
});
</script>

<style scoped>
.imports-page { max-width: 1440px; }
.setup-panel { background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; padding: 16px; }
.upload-grid { align-items: center; display: grid; gap: 12px; grid-template-columns: 1.2fr 1fr 1.4fr auto auto; }
.batch-layout { display: grid; gap: 16px; grid-template-columns: minmax(360px, 0.85fr) minmax(0, 1.55fr); margin-top: 16px; }
.detail-panel { min-width: 0; }
.detail-header { align-items: center; display: flex; gap: 16px; justify-content: space-between; }
.detail-header h3 { font-size: 18px; margin: 0 0 4px; }
.count-strip { display: flex; flex-wrap: wrap; gap: 8px; margin: 12px 0; }
.row-detail { display: grid; gap: 12px; grid-template-columns: repeat(2, minmax(0, 1fr)); padding: 8px 16px 16px; }
.resolve-controls { align-items: center; display: grid; gap: 8px; grid-template-columns: minmax(120px, 1fr) minmax(120px, 1fr) auto; }
.status-filter { width: 150px; }
pre { background: #f8fafc; border: 1px solid #d1d5db; border-radius: 6px; max-height: 240px; overflow: auto; padding: 10px; white-space: pre-wrap; }
@media (max-width: 1180px) {
  .upload-grid, .batch-layout, .row-detail { grid-template-columns: 1fr; }
}
</style>
