<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2>Quarantine</h2>
        <div class="muted">Rows preserved before QC ingestion.</div>
      </div>
      <div class="toolbar">
        <el-select v-model="statusFilter" class="status-filter" @change="loadQueue">
          <el-option label="Open" value="open" />
          <el-option label="Reviewed" value="reviewed" />
          <el-option label="Rejected" value="rejected" />
        </el-select>
        <el-button @click="loadQueue">Refresh</el-button>
      </div>
    </div>

    <el-card>
      <el-table v-loading="loading" :data="rows" stripe class="full-width">
        <el-table-column type="expand">
          <template #default="{ row }">
            <div class="details-grid">
              <div>
                <h4>Payload</h4>
                <pre>{{ pretty(row.payload) }}</pre>
              </div>
              <div>
                <h4>Context</h4>
                <pre>{{ pretty(row.context) }}</pre>
              </div>
              <div>
                <h4>Failures</h4>
                <pre>{{ pretty(row.failures) }}</pre>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="Status" width="110">
          <template #default="{ row }">
            <el-tag :type="statusTag(row.status)">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="reason" label="Reason" width="180" />
        <el-table-column prop="stream_id" label="Stream" min-width="180" />
        <el-table-column label="Created" min-width="180">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column prop="reason_detail" label="Detail" min-width="260" />
        <el-table-column label="Review" min-width="320">
          <template #default="{ row }">
            <div v-if="canApprove && row.status === 'open'" class="review-controls">
              <el-select v-model="row.review_status" class="review-status">
                <el-option label="Reviewed" value="reviewed" />
                <el-option label="Rejected" value="rejected" />
              </el-select>
              <el-input v-model="row.review_reason" placeholder="Reason" />
              <el-button type="primary" @click="saveReview(row)">Save</el-button>
            </div>
            <div v-else class="muted small-text">
              {{ row.review_reason || row.reviewed_by || "No review recorded" }}
            </div>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import { api } from "../api/client";
import type {
  QCRecordQuarantineOut,
  QuarantineReviewIn,
  QuarantineStatus,
} from "../api/contracts";
import { canApprove } from "../api/session";

type ReviewStatus = "reviewed" | "rejected";
type QueueRow = QCRecordQuarantineOut & {
  review_status: ReviewStatus;
  review_reason: string;
};

const rows = ref<QueueRow[]>([]);
const loading = ref(false);
const statusFilter = ref<QuarantineStatus>("open");

function toQueueRow(row: QCRecordQuarantineOut): QueueRow {
  return {
    ...row,
    review_status: "reviewed",
    review_reason: "",
  };
}

function pretty(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

function formatDate(value: string): string {
  return new Date(value).toLocaleString();
}

function statusTag(status: QuarantineStatus): "success" | "warning" | "danger" | "info" {
  if (status === "reviewed") return "success";
  if (status === "rejected") return "danger";
  if (status === "open") return "warning";
  return "info";
}

async function loadQueue(): Promise<void> {
  loading.value = true;
  try {
    const path = `/qc/quarantine?status=${encodeURIComponent(statusFilter.value)}`;
    const response = await api.get<QCRecordQuarantineOut[]>(path);
    rows.value = response.map(toQueueRow);
  } finally {
    loading.value = false;
  }
}

async function saveReview(row: QueueRow): Promise<void> {
  const reason = row.review_reason.trim();
  if (!reason) {
    ElMessage.error("Reason is required");
    return;
  }
  const payload: QuarantineReviewIn = {
    status: row.review_status,
    review_reason: reason,
  };
  await api.patch<QCRecordQuarantineOut>(`/qc/quarantine/${row.id}`, payload);
  ElMessage.success("Review saved");
  await loadQueue();
}

onMounted(() => {
  void loadQueue();
});
</script>

<style scoped>
.toolbar,
.review-controls {
  display: flex;
  gap: 8px;
  align-items: center;
}

.status-filter {
  width: 150px;
}

.review-status {
  width: 130px;
  flex: 0 0 auto;
}

.details-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  padding: 8px 16px 16px;
}

pre {
  max-height: 260px;
  overflow: auto;
  padding: 10px;
  border: 1px solid #d1d5db;
  background: #f8fafc;
  border-radius: 6px;
  font-size: 12px;
  white-space: pre-wrap;
}
</style>
