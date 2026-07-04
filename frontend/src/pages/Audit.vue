<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2>Audit Log</h2>
        <div class="muted">Filter, inspect, and export recorded QC workflow actions.</div>
      </div>
      <div class="toolbar">
        <el-button :disabled="!filteredEntries.length" @click="exportJson">Export JSON</el-button>
        <el-button :disabled="!filteredEntries.length" @click="exportCsv">Export CSV</el-button>
        <el-button @click="loadAudit">Refresh</el-button>
      </div>
    </div>

    <div class="toolbar audit-filters">
      <el-select v-model="entityTypeFilter" clearable placeholder="Entity" style="width: 160px">
        <el-option v-for="entity in entityTypes" :key="entity" :label="entity" :value="entity" />
      </el-select>
      <el-select v-model="actionFilter" clearable placeholder="Action" style="width: 190px">
        <el-option v-for="action in actions" :key="action" :label="action" :value="action" />
      </el-select>
      <el-select v-model="roleFilter" clearable placeholder="Role" style="width: 160px">
        <el-option v-for="role in roleOptions" :key="role" :label="role" :value="role" />
      </el-select>
      <el-input v-model="actorFilter" clearable placeholder="Actor" style="width: 180px" />
      <el-input v-model="streamFilter" clearable placeholder="Stream" style="width: 180px" />
      <el-input-number v-model="apiKeyFilter" :min="1" placeholder="API key" style="width: 140px" />
      <el-date-picker
        v-model="dateRange"
        type="daterange"
        start-placeholder="Start"
        end-placeholder="End"
        unlink-panels
      />
      <el-button @click="clearFilters">Clear</el-button>
    </div>

    <div class="muted audit-count">
      Showing {{ filteredEntries.length }} of {{ entries.length }} entries
    </div>

    <el-table :data="filteredEntries" stripe row-key="timestamp" class="full-width">
      <el-table-column type="expand">
        <template #default="{ row }">
          <div class="audit-detail">
            <div>
              <h3>Changed Fields</h3>
              <el-tag v-for="field in changedFields(row)" :key="field" class="field-tag">
                {{ field }}
              </el-tag>
              <div v-if="!changedFields(row).length" class="muted">No field-level change detected.</div>
            </div>
            <div class="json-grid">
              <div>
                <h3>Before</h3>
                <pre>{{ formatJson(row.before) }}</pre>
              </div>
              <div>
                <h3>After</h3>
                <pre>{{ formatJson(row.after) }}</pre>
              </div>
            </div>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="Timestamp" width="180">
        <template #default="{ row }">
          {{ formatTimestamp(row.timestamp) }}
        </template>
      </el-table-column>
      <el-table-column prop="entity_type" label="Entity" width="130" />
      <el-table-column prop="entity_id" label="Entity ID" width="120" />
      <el-table-column prop="action" label="Action" width="180" />
      <el-table-column prop="actor" label="Actor" min-width="170" />
      <el-table-column label="Role" width="130">
        <template #default="{ row }">
          {{ row.actor_role ?? "-" }}
        </template>
      </el-table-column>
      <el-table-column label="API Key" width="100">
        <template #default="{ row }">
          {{ row.api_key_id ?? "-" }}
        </template>
      </el-table-column>
      <el-table-column label="Stream" width="170">
        <template #default="{ row }">
          {{ streamIds(row).join(", ") || "-" }}
        </template>
      </el-table-column>
      <el-table-column prop="reason" label="Reason" min-width="220" show-overflow-tooltip />
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import { api } from "../api/client";
import type { AuditEntryOut, Role } from "../api/contracts";

type DateRange = [Date, Date];
type JsonRecord = Record<string, unknown>;

const entries = ref<AuditEntryOut[]>([]);
const entityTypeFilter = ref("");
const actionFilter = ref("");
const roleFilter = ref<Role | "">("");
const actorFilter = ref("");
const streamFilter = ref("");
const apiKeyFilter = ref<number | undefined>();
const dateRange = ref<DateRange | null>(null);

const roleOptions: Role[] = ["admin", "auditor", "data_steward", "qa_manager", "qc_analyst", "supervisor"];
const entityTypes = computed(() => uniqueSorted(entries.value.map((entry) => entry.entity_type)));
const actions = computed(() => uniqueSorted(entries.value.map((entry) => entry.action)));
const filteredEntries = computed(() => entries.value.filter(matchesFilters));

async function loadAudit(): Promise<void> {
  entries.value = await api.get<AuditEntryOut[]>("/audit");
}

function uniqueSorted(values: string[]): string[] {
  return [...new Set(values.filter(Boolean))].sort((left, right) => left.localeCompare(right));
}

function includesText(value: string | null | undefined, query: string): boolean {
  return value?.toLowerCase().includes(query.trim().toLowerCase()) ?? false;
}

function streamIds(entry: AuditEntryOut): string[] {
  const values = new Set<string>();
  collectFieldValues(entry.before, "stream_id", values);
  collectFieldValues(entry.after, "stream_id", values);
  if (entry.entity_type === "stream_config" && entry.entity_id) {
    values.add(entry.entity_id);
  }
  return [...values].sort();
}

function collectFieldValues(value: unknown, key: string, values: Set<string>): void {
  if (!value || typeof value !== "object") {
    return;
  }
  if (Array.isArray(value)) {
    value.forEach((item) => collectFieldValues(item, key, values));
    return;
  }
  for (const [field, fieldValue] of Object.entries(value as JsonRecord)) {
    if (field === key && typeof fieldValue === "string") {
      values.add(fieldValue);
    }
    collectFieldValues(fieldValue, key, values);
  }
}

function matchesFilters(entry: AuditEntryOut): boolean {
  if (entityTypeFilter.value && entry.entity_type !== entityTypeFilter.value) {
    return false;
  }
  if (actionFilter.value && entry.action !== actionFilter.value) {
    return false;
  }
  if (roleFilter.value && entry.actor_role !== roleFilter.value) {
    return false;
  }
  if (actorFilter.value && !includesText(entry.actor, actorFilter.value)) {
    return false;
  }
  if (apiKeyFilter.value && entry.api_key_id !== apiKeyFilter.value) {
    return false;
  }
  if (streamFilter.value && !streamIds(entry).some((stream) => includesText(stream, streamFilter.value))) {
    return false;
  }
  if (!dateRange.value) {
    return true;
  }
  const [start, end] = dateRange.value;
  const timestamp = new Date(entry.timestamp).getTime();
  const startMs = new Date(start).setHours(0, 0, 0, 0);
  const endMs = new Date(end).setHours(23, 59, 59, 999);
  return timestamp >= startMs && timestamp <= endMs;
}

function clearFilters(): void {
  entityTypeFilter.value = "";
  actionFilter.value = "";
  roleFilter.value = "";
  actorFilter.value = "";
  streamFilter.value = "";
  apiKeyFilter.value = undefined;
  dateRange.value = null;
}

function formatTimestamp(value: string): string {
  return new Date(value).toLocaleString();
}

function formatJson(value: unknown): string {
  return value == null ? "-" : JSON.stringify(value, null, 2);
}

function changedFields(entry: AuditEntryOut): string[] {
  const before = flatten(entry.before);
  const after = flatten(entry.after);
  return uniqueSorted([...Object.keys(before), ...Object.keys(after)]).filter((key) => before[key] !== after[key]);
}

function flatten(value: unknown, prefix = "", output: Record<string, string> = {}): Record<string, string> {
  if (!value || typeof value !== "object") {
    if (prefix) {
      output[prefix] = JSON.stringify(value) ?? String(value);
    }
    return output;
  }
  if (Array.isArray(value)) {
    value.forEach((item, index) => flatten(item, `${prefix}[${index}]`, output));
    return output;
  }
  for (const [key, child] of Object.entries(value as JsonRecord)) {
    flatten(child, prefix ? `${prefix}.${key}` : key, output);
  }
  return output;
}

function downloadFile(content: string, mimeType: string, filename: string): void {
  const url = URL.createObjectURL(new Blob([content], { type: mimeType }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
  ElMessage.success(`Exported ${filteredEntries.value.length} audit entries`);
}

function exportJson(): void {
  downloadFile(JSON.stringify(filteredEntries.value, null, 2), "application/json", "bayesianqc-audit.json");
}

function csvCell(value: unknown): string {
  const text = value == null ? "" : typeof value === "string" ? value : JSON.stringify(value) ?? String(value);
  return `"${text.replaceAll("\"", "\"\"")}"`;
}

function exportCsv(): void {
  const headers = ["timestamp", "entity_type", "entity_id", "action", "actor", "actor_role", "api_key_id", "reason"];
  const rows = filteredEntries.value.map((entry) =>
    headers.map((key) => csvCell(entry[key as keyof AuditEntryOut])).join(",")
  );
  downloadFile([headers.join(","), ...rows].join("\n"), "text/csv", "bayesianqc-audit.csv");
}

onMounted(loadAudit);
</script>

<style scoped>
.audit-filters {
  align-items: center;
  margin-bottom: 10px;
}

.audit-count {
  margin-bottom: 12px;
}

.audit-detail {
  display: grid;
  gap: 14px;
  padding: 4px 12px 16px;
}

.field-tag {
  margin: 0 6px 6px 0;
}

.json-grid {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
}

pre {
  max-height: 280px;
  overflow: auto;
  margin: 0;
  padding: 12px;
  background: #111827;
  color: #e5e7eb;
  border-radius: 6px;
}
</style>
