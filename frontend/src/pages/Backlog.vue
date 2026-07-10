<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2>QC Backlog</h2>
        <div class="muted">Scheduled and requested QC runs by bench, instrument, group, or assignee.</div>
      </div>
      <div class="toolbar">
        <el-button :loading="loading" @click="loadBacklog">Refresh</el-button>
        <el-button v-if="canIngestQc" type="primary" @click="showCreate = true">New QC</el-button>
      </div>
    </div>

    <el-alert v-if="loadError" type="error" :closable="false" show-icon class="section-card">
      <template #title>Backlog data could not be loaded.</template>
      <el-button size="small" @click="loadPage">Retry</el-button>
    </el-alert>

    <el-card class="section-card">
      <el-tabs v-model="viewMode" @tab-change="applyView">
        <el-tab-pane label="All" name="all" />
        <el-tab-pane label="Mine" name="mine" />
        <el-tab-pane label="Instrument" name="instrument" />
        <el-tab-pane label="Bench" name="bench" />
        <el-tab-pane label="Group" name="group" />
      </el-tabs>
      <div class="toolbar">
        <el-select v-model="filters.status" multiple collapse-tags placeholder="Status" @change="loadBacklog">
          <el-option label="open" value="open" />
          <el-option label="in_progress" value="in_progress" />
          <el-option label="completed" value="completed" />
          <el-option label="canceled" value="canceled" />
        </el-select>
        <el-input v-model="filters.instrument" placeholder="Instrument" clearable @change="loadBacklog" />
        <el-input v-model="filters.lab_bench" placeholder="Bench" clearable @change="loadBacklog" />
        <el-input v-model="filters.assignment_group" placeholder="Group" clearable @change="loadBacklog" />
        <el-input v-model="filters.assigned_to" placeholder="Assignee" clearable @change="loadBacklog" />
      </div>
    </el-card>

    <el-table v-loading="loading" :data="items" stripe class="full-width">
      <el-table-column label="Due" width="190">
        <template #default="{ row }">
          <el-tag :type="dueTag(row)">{{ dueLabel(row) }}</el-tag>
          <div class="small-text muted">{{ formatDateTime(row.due_at) }}</div>
        </template>
      </el-table-column>
      <el-table-column label="QC" min-width="260">
        <template #default="{ row }">
          <strong>{{ row.analyte }} {{ row.qc_level }}</strong>
          <div class="small-text muted">{{ row.method }} · {{ row.instrument }}</div>
        </template>
      </el-table-column>
      <el-table-column label="Reference" min-width="180">
        <template #default="{ row }">
          <span>{{ row.reference_material_label || "Control material" }}</span>
          <div class="small-text muted">{{ row.reference_material_lot }}</div>
        </template>
      </el-table-column>
      <el-table-column prop="lab_bench" label="Bench" />
      <el-table-column prop="assignment_group" label="Group" />
      <el-table-column prop="assigned_to" label="Assignee" />
      <el-table-column label="Status" width="150">
        <template #default="{ row }">
          <el-tag>{{ row.status }}</el-tag>
          <div class="small-text muted">{{ row.priority }} · {{ row.source }}</div>
        </template>
      </el-table-column>
      <el-table-column label="Actions" width="240">
        <template #default="{ row }">
          <el-button v-if="canIngestQc && row.status === 'open'" size="small" @click="claim(row)">Claim</el-button>
          <el-button v-if="canIngestQc && row.status !== 'completed' && row.status !== 'canceled'" size="small" @click="runQc(row)">
            Run
          </el-button>
          <el-button v-if="canApprove && row.status !== 'completed' && row.status !== 'canceled'" size="small" type="danger" plain @click="cancel(row)">
            Cancel
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="showCreate" title="New QC Backlog Item" width="640">
      <el-form label-position="top" class="entry-grid">
        <el-form-item label="Stream">
          <el-select v-model="draft.stream_id" filterable class="full-width">
            <el-option
              v-for="stream in streams"
              :key="stream.stream_id"
              :label="`${stream.analyte} ${stream.qc_level} - ${stream.instrument}`"
              :value="stream.stream_id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="Source">
          <el-select v-model="draft.source" class="full-width">
            <el-option label="requested" value="requested" />
            <el-option label="scheduled" value="scheduled" />
          </el-select>
        </el-form-item>
        <el-form-item label="Due">
          <el-date-picker v-model="draft.due_at" type="datetime" class="full-width" />
        </el-form-item>
        <el-form-item label="Priority">
          <el-select v-model="draft.priority" class="full-width">
            <el-option label="routine" value="routine" />
            <el-option label="soon" value="soon" />
            <el-option label="urgent" value="urgent" />
          </el-select>
        </el-form-item>
        <el-form-item label="Bench"><el-input v-model="draft.lab_bench" /></el-form-item>
        <el-form-item label="Group"><el-input v-model="draft.assignment_group" /></el-form-item>
        <el-form-item label="Assignee"><el-input v-model="draft.assigned_to" /></el-form-item>
        <el-form-item label="Reference Label"><el-input v-model="draft.reference_material_label" /></el-form-item>
        <el-form-item label="Notes"><el-input v-model="draft.notes" type="textarea" :rows="2" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreate = false">Cancel</el-button>
        <el-button type="primary" :disabled="!draft.stream_id" @click="createItem">Create</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { api } from "../api/client";
import type {
  QCBacklogItemIn,
  QCBacklogItemOut,
  QCBacklogItemUpdate,
  QCBacklogPriority,
  QCBacklogSource,
  QCBacklogStatus,
  StreamCatalogOut,
} from "../api/contracts";
import { canApprove, canIngestQc, defaultScopeFilter, loadSessionUser, sessionUser } from "../api/session";
import { formatDateTime } from "./ingestionWorkflow";
import { loadStreamCatalog } from "../api/streamCatalog";

type Filters = {
  status: QCBacklogStatus[];
  instrument: string;
  lab_bench: string;
  assignment_group: string;
  assigned_to: string;
};

const router = useRouter();
const items = ref<QCBacklogItemOut[]>([]);
const streams = ref<StreamCatalogOut[]>([]);
const showCreate = ref(false);
const loading = ref(false);
const loadError = ref(false);
const viewMode = ref("all");
const filters = reactive<Filters>({
  status: ["open", "in_progress"],
  instrument: "",
  lab_bench: "",
  assignment_group: "",
  assigned_to: "",
});
const draft = reactive({
  source: "requested" as QCBacklogSource,
  stream_id: "",
  due_at: new Date(),
  priority: "routine" as QCBacklogPriority,
  lab_bench: "",
  assignment_group: "",
  assigned_to: "",
  reference_material_label: "",
  notes: "",
});

function currentActor(): string {
  const user = sessionUser.value;
  return user ? `${user.role}:key-${user.api_key_id ?? "unknown"}` : "";
}

function compact(value: string): string | null {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function applyScopeDefaults(): void {
  const bench = defaultScopeFilter("lab_benches");
  const group = defaultScopeFilter("assignment_groups");
  if (bench) {
    filters.lab_bench ||= bench;
    draft.lab_bench ||= bench;
  }
  if (group) {
    filters.assignment_group ||= group;
    draft.assignment_group ||= group;
  }
}

function buildQuery(): string {
  const params = new URLSearchParams();
  for (const status of filters.status) params.append("status", status);
  for (const key of ["instrument", "lab_bench", "assignment_group", "assigned_to"] as const) {
    const value = compact(filters[key]);
    if (value) params.set(key, value);
  }
  return params.toString();
}

async function loadBacklog(): Promise<void> {
  loading.value = true;
  loadError.value = false;
  try {
    const query = buildQuery();
    items.value = await api.get<QCBacklogItemOut[]>(`/qc/backlog${query ? `?${query}` : ""}`);
  } catch { items.value = []; loadError.value = true; }
  finally { loading.value = false; }
}

async function loadStreams(): Promise<void> {
  try {
    streams.value = await loadStreamCatalog();
    draft.stream_id = streams.value[0]?.stream_id ?? "";
  } catch { streams.value = []; loadError.value = true; }
}

async function loadPage(): Promise<void> {
  await Promise.all([loadStreams(), loadBacklog()]);
}

function applyView(): void {
  if (viewMode.value === "mine") filters.assigned_to = currentActor();
  if (viewMode.value !== "mine") filters.assigned_to = "";
  void loadBacklog();
}

function dueLabel(row: QCBacklogItemOut): string {
  if (row.status === "completed" || row.status === "canceled") return row.status;
  return new Date(row.due_at).getTime() < Date.now() ? "overdue" : "due";
}

function dueTag(row: QCBacklogItemOut): "success" | "warning" | "danger" | "info" {
  if (row.status === "completed") return "success";
  if (row.status === "canceled") return "info";
  return new Date(row.due_at).getTime() < Date.now() ? "danger" : "warning";
}

async function createItem(): Promise<void> {
  const payload: QCBacklogItemIn = {
    ...draft,
    due_at: draft.due_at.toISOString(),
    lab_bench: compact(draft.lab_bench),
    assignment_group: compact(draft.assignment_group),
    assigned_to: compact(draft.assigned_to),
    reference_material_label: compact(draft.reference_material_label),
    notes: compact(draft.notes),
  };
  await api.post<QCBacklogItemOut>("/qc/backlog", payload);
  showCreate.value = false;
  ElMessage.success("QC backlog item created");
  await loadBacklog();
}

async function claim(row: QCBacklogItemOut): Promise<void> {
  const payload: QCBacklogItemUpdate = { status: "in_progress", assigned_to: currentActor(), reason: "claimed" };
  await api.patch<QCBacklogItemOut>(`/qc/backlog/${row.id}`, payload);
  await loadBacklog();
}

async function cancel(row: QCBacklogItemOut): Promise<void> {
  const reason = await ElMessageBox.prompt("Reason", "Cancel QC Backlog Item").catch(() => null);
  if (!reason) return;
  await api.patch<QCBacklogItemOut>(`/qc/backlog/${row.id}`, { status: "canceled", reason: reason.value });
  await loadBacklog();
}

function runQc(row: QCBacklogItemOut): void {
  router.push(`/ingest?backlog=${row.id}`);
}

onMounted(async () => {
  await loadSessionUser().catch(() => null);
  applyScopeDefaults();
  await loadPage();
});
</script>
