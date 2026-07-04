<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2>QC Ingestion</h2>
        <div class="muted">Manual QC entry and CSV ingestion.</div>
      </div>
      <el-button @click="loadStreams">Reload Streams</el-button>
    </div>

    <el-alert v-if="backlogItem" class="section-card" type="info" :closable="false" :title="`Running backlog #${backlogItem.id}: ${backlogItem.instrument} ${backlogItem.qc_level} due ${formatDateTime(backlogItem.due_at)}`" />

    <el-card class="section-card">
      <div class="manual-header">
        <h3>Manual QC Entry</h3>
        <el-select v-model="selectedStreamId" filterable placeholder="Recent stream" class="stream-picker">
          <el-option
            v-for="stream in streams"
            :key="stream.stream_id"
            :label="`${stream.analyte} ${stream.qc_level} - ${stream.instrument}`"
            :value="stream.stream_id"
          />
        </el-select>
      </div>

      <div class="entry-layout">
        <el-form label-position="top" class="entry-grid">
          <el-form-item label="Timestamp">
            <el-date-picker v-model="common.timestamp" type="datetime" class="full-width" />
          </el-form-item>
          <el-form-item label="Run / Batch ID">
            <el-input v-model="common.run_id" />
          </el-form-item>
          <el-form-item label="Operator">
            <el-input v-model="common.operator_id" />
          </el-form-item>
          <el-form-item label="Reagent Lot">
            <el-input v-model="common.reagent_lot" />
          </el-form-item>
          <el-form-item label="Calibration Status">
            <el-input v-model="common.calibration_status" />
          </el-form-item>
          <el-form-item label="Entry Source">
            <el-select v-model="common.entry_source" class="full-width">
              <el-option label="manual" value="manual" />
              <el-option label="automated" value="automated" />
            </el-select>
          </el-form-item>
          <el-form-item label="Idempotency Key Prefix">
            <el-input v-model="common.idempotency_key" />
          </el-form-item>
          <el-form-item label="Comments">
            <el-input v-model="common.comments" type="textarea" :rows="2" />
          </el-form-item>
        </el-form>

        <div v-if="selectedStream" class="context-panel">
          <div class="context-title">Stream Context</div>
          <div class="context-row"><span>Analyte</span><strong>{{ selectedStream.analyte }}</strong></div>
          <div class="context-row"><span>QC Level</span><strong>{{ selectedStream.qc_level }}</strong></div>
          <div class="context-row"><span>Instrument</span><strong>{{ selectedStream.instrument }}</strong></div>
          <div class="context-row"><span>Method</span><strong>{{ selectedStream.method }}</strong></div>
          <div class="context-row"><span>Control Lot</span><strong>{{ selectedStream.control_material_lot }}</strong></div>
          <div class="context-row"><span>Units</span><strong>{{ selectedStream.units }}</strong></div>
          <div class="limit-grid">
            <div><span>Target</span><strong>{{ formatNumber(selectedStream.target_value) }}</strong></div>
            <div><span>Sigma</span><strong>{{ formatNumber(selectedStream.sigma) }}</strong></div>
            <div><span>Warning</span><strong>{{ limitText(selectedStream, selectedStream.warning_limit_sd) }}</strong></div>
            <div><span>Action</span><strong>{{ limitText(selectedStream, selectedStream.action_limit_sd) }}</strong></div>
          </div>
          <div v-if="latestRecord" class="recent-box">
            <span>Latest point</span>
            <strong>{{ formatDateTime(latestRecord.timestamp) }} · {{ formatNumber(latestRecord.result_value) }}</strong>
            <span>{{ latestRecord.disposition ?? "not evaluated" }}</span>
          </div>
          <el-tooltip v-if="latestRisk" placement="top" :content="bayesianRiskTooltip">
            <div class="risk-grid" tabindex="0">
              <div><span>Risk</span><strong>{{ latestRisk.risk_score }}</strong></div>
              <div><span>P warn</span><strong>{{ formatPercent(latestRisk.probability_outside_warning) }}</strong></div>
              <div><span>P action</span><strong>{{ formatPercent(latestRisk.probability_outside_limits) }}</strong></div>
              <div><span>Posterior mean</span><strong>{{ formatNumber(latestRisk.posterior_mean) }}</strong></div>
            </div>
          </el-tooltip>
          <div v-else class="muted">No Bayesian risk is available for this stream.</div>
        </div>
      </div>

      <div class="batch-actions">
        <el-button @click="addSelectedRow">Add Level</el-button>
        <el-button :disabled="!selectedStream || peerLevelCount < 2" @click="addMatchingRows">Add Matching Levels</el-button>
        <el-button :disabled="rows.length < 2" @click="clearRows">Clear Batch</el-button>
        <el-button v-if="canIngestQc" type="primary" :disabled="!canSubmit" @click="submitBatch">
          Submit {{ rows.length }} Record{{ rows.length === 1 ? "" : "s" }}
        </el-button>
      </div>

      <el-table :data="rows" stripe class="full-width">
        <el-table-column label="QC Level" min-width="210">
          <template #default="{ row }">
            <el-select v-model="row.stream_id" filterable class="full-width" @change="syncRowToStream(row)">
              <el-option
                v-for="stream in streams"
                :key="stream.stream_id"
                :label="`${stream.qc_level} - ${stream.stream_id}`"
                :value="stream.stream_id"
              />
            </el-select>
            <el-tag v-if="row.qc_backlog_item_id" size="small" type="info">Backlog #{{ row.qc_backlog_item_id }}</el-tag>
            <div class="muted small-text">{{ streamSummary(row.stream_id) }}</div>
          </template>
        </el-table-column>
        <el-table-column label="Result" width="140">
          <template #default="{ row }">
            <el-input-number v-model="row.result_value" class="full-width" :step="0.1" />
          </template>
        </el-table-column>
        <el-table-column label="Limits" min-width="170">
          <template #default="{ row }">
            <div v-if="streamFor(row)" class="small-text">
              Target {{ formatNumber(streamFor(row)?.target_value) }};
              warn {{ limitText(streamFor(row), streamFor(row)?.warning_limit_sd) }};
              action {{ limitText(streamFor(row), streamFor(row)?.action_limit_sd) }}
            </div>
          </template>
        </el-table-column>
        <el-table-column label="Row Comments" min-width="150">
          <template #default="{ row }">
            <el-input v-model="row.comments" />
          </template>
        </el-table-column>
        <el-table-column label="Validation" min-width="160">
          <template #default="{ row }">
            <el-tag v-if="rowErrors(row).length === 0 && rowWarnings(row).length === 0" type="success">Ready</el-tag>
            <el-tag v-for="error in rowErrors(row)" :key="error" type="danger" class="tag-gap">{{ error }}</el-tag>
            <el-tag v-for="warning in rowWarnings(row)" :key="warning" type="warning" class="tag-gap">{{ warning }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="Status" min-width="110">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)">{{ row.status }}</el-tag>
            <div v-if="row.message" class="muted small-text">{{ row.message }}</div>
          </template>
        </el-table-column>
        <el-table-column label="" width="96">
          <template #default="{ row }">
            <el-button text type="danger" @click="removeRow(row.id)">Remove</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div v-if="!canIngestQc" class="muted permission-note">Current role cannot ingest QC records.</div>
      <div v-if="submittedRunId" class="comment-panel">
        <QCCommentThread target-type="qc_run" :target-id="submittedRunId" title="Run Comments" />
      </div>
    </el-card>

    <el-card>
      <h3>CSV Upload</h3>
      <el-upload v-if="canIngestQc" class="upload" drag action="" :http-request="uploadCsv" :show-file-list="false">
        <div class="el-upload__text">Drop CSV here or click to upload</div>
      </el-upload>
      <div v-if="uploadSummary" class="muted summary-text">{{ uploadSummary }}</div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { ElMessage } from "element-plus";
import type { UploadRequestOptions } from "element-plus/es/components/upload/src/upload";
import { api } from "../api/client";
import type { BayesianRisk, CsvIngestResult, IngestionResult, QCBacklogItemOut, QCRecordChartOutEvaluated, QuarantineResult, StreamChartOutEvaluated, StreamConfigOut } from "../api/contracts";
import { canIngestQc } from "../api/session";
import QCCommentThread from "../components/QCCommentThread.vue";
import { bayesianRiskHelpText } from "./chartRisk";
import { buildQcPayload, formatDateTime, formatNumber, formatPercent, latestChartRecord, limitValue, makeBatchRow, matchingLevelStreams, readManualRecent, statusTagType, type ManualBatchRow, type ManualCommonFields, validateManualRow, writeManualRecent } from "./ingestionWorkflow";

const route = useRoute();
const streams = ref<StreamConfigOut[]>([]);
const rows = ref<ManualBatchRow[]>([]);
const selectedStreamId = ref("");
const chartRecords = ref<QCRecordChartOutEvaluated[]>([]);
const backlogItem = ref<QCBacklogItemOut | null>(null);
const uploadSummary = ref<string | null>(null);
const submittedRunId = ref<string | null>(null);
let nextRowId = 1;

const common = reactive<ManualCommonFields>({
  timestamp: new Date(),
  run_id: `ui-${Date.now()}`,
  operator_id: "",
  reagent_lot: "",
  calibration_status: "ok",
  entry_source: "manual",
  comments: "",
  idempotency_key: "",
});

const streamMap = computed(() => new Map(streams.value.map((stream) => [stream.stream_id, stream])));
const selectedStream = computed(() => streamMap.value.get(selectedStreamId.value));
const latestRecord = computed(() => latestChartRecord(chartRecords.value));
const latestRisk = computed<BayesianRisk | null>(() => latestRecord.value?.bayesian_risk ?? null);
const bayesianRiskTooltip = bayesianRiskHelpText("through the latest point shown");
const peerLevelCount = computed(() =>
  selectedStream.value ? matchingLevelStreams(streams.value, selectedStream.value).length : 0
);
const canSubmit = computed(() => canIngestQc.value && rows.value.length > 0 && rows.value.every((row) => rowErrors(row).length === 0));

async function loadStreams() {
  streams.value = await api.get<StreamConfigOut[]>("/streams");
  if (!selectedStreamId.value || !streamMap.value.has(selectedStreamId.value)) {
    selectedStreamId.value = streams.value[0]?.stream_id ?? "";
  }
  if (rows.value.length === 0 && selectedStream.value) {
    addSelectedRow();
  }
}

async function loadChartContext(streamId: string) {
  if (!streamId) {
    chartRecords.value = [];
    return;
  }
  const path = `/streams/${encodeURIComponent(streamId)}/chart?limit=6&include_evaluations=true`;
  const chart = await api.get<StreamChartOutEvaluated>(path);
  chartRecords.value = chart.records;
}

async function loadBacklogHandoff(): Promise<void> {
  const rawId = Array.isArray(route.query.backlog) ? route.query.backlog[0] : route.query.backlog;
  const itemId = Number(rawId);
  if (!Number.isInteger(itemId) || itemId <= 0) {
    backlogItem.value = null;
    return;
  }
  const item = await api.get<QCBacklogItemOut>(`/qc/backlog/${itemId}`);
  const stream = streamMap.value.get(item.stream_id);
  if (!stream) {
    ElMessage.error("Backlog stream is not available in active streams");
    return;
  }
  backlogItem.value = item;
  selectedStreamId.value = item.stream_id;
  common.run_id = `backlog-${item.id}-${Date.now()}`;
  common.comments = item.notes ?? "";
  rows.value = [makeBatchRow(stream, nextRowId++, item.id)];
}

function streamFor(row: ManualBatchRow): StreamConfigOut | undefined {
  return streamMap.value.get(row.stream_id);
}

function streamSummary(streamId: string): string {
  const stream = streamMap.value.get(streamId);
  return stream ? `${stream.analyte} · ${stream.instrument} · ${stream.control_material_lot} · ${stream.units}` : "";
}

function limitText(stream: StreamConfigOut | undefined, sd: number | undefined): string {
  if (!stream || sd === undefined) return "-";
  return `${formatNumber(limitValue(stream, sd, -1))} - ${formatNumber(limitValue(stream, sd, 1))}`;
}

function validation(row: ManualBatchRow) {
  return validateManualRow(row, streamFor(row), common.timestamp);
}

function rowErrors(row: ManualBatchRow): string[] {
  return validation(row).errors;
}

function rowWarnings(row: ManualBatchRow): string[] {
  return validation(row).warnings;
}

function isQuarantineResult(response: IngestionResult | QuarantineResult): response is QuarantineResult {
  return response.status === "quarantined";
}

function addSelectedRow(): void {
  if (selectedStream.value) {
    rows.value.push(makeBatchRow(selectedStream.value, nextRowId++));
  }
}

function addMatchingRows(): void {
  if (!selectedStream.value) return;
  const existing = new Set(rows.value.map((row) => row.stream_id));
  for (const stream of matchingLevelStreams(streams.value, selectedStream.value)) {
    if (!existing.has(stream.stream_id)) {
      rows.value.push(makeBatchRow(stream, nextRowId++));
    }
  }
}

function syncRowToStream(row: ManualBatchRow): void {
  const stream = streamFor(row);
  row.result_value = stream?.target_value ?? null;
  row.status = "draft";
  row.message = "";
}

function removeRow(id: number): void {
  rows.value = rows.value.filter((row) => row.id !== id);
}

function clearRows(): void {
  rows.value = [];
  addSelectedRow();
}

async function submitBatch(): Promise<void> {
  let accepted = 0;
  let quarantined = 0;
  let latestRunId: string | null = null;
  for (const [index, row] of rows.value.entries()) {
    const stream = streamFor(row);
    const errors = rowErrors(row);
    if (!stream || errors.length > 0) {
      row.status = "error";
      row.message = errors.join(" ");
      continue;
    }
    try {
      const headers = common.idempotency_key.trim()
        ? { "Idempotency-Key": `${common.idempotency_key.trim()}-${index + 1}` }
        : undefined;
      const response = await api.post<IngestionResult | QuarantineResult>(
        "/qc/records",
        buildQcPayload(row, stream, common),
        headers
      );
      if (isQuarantineResult(response)) {
        row.status = "quarantined";
        row.message = `${response.quarantine.reason}: ${response.quarantine.reason_detail}`;
        quarantined += 1;
      } else {
        row.status = "accepted";
        row.message = `${response.qc.disposition}; ${response.duplicate}`;
        latestRunId = response.qc.record.run_id ?? latestRunId;
        accepted += 1;
        writeManualRecent(window.localStorage, {
          stream_id: stream.stream_id,
          run_id: common.run_id,
          operator_id: common.operator_id,
          reagent_lot: common.reagent_lot,
          calibration_status: common.calibration_status,
        });
      }
    } catch (error) {
      row.status = "error";
      row.message = error instanceof Error && error.message ? error.message : "Failed to ingest record";
    }
  }
  if (accepted > 0) {
    submittedRunId.value = latestRunId;
    ElMessage.success(`Accepted ${accepted} record${accepted === 1 ? "" : "s"}`);
    await loadChartContext(selectedStreamId.value);
  }
  if (quarantined > 0) {
    ElMessage.warning(`Quarantined ${quarantined} record${quarantined === 1 ? "" : "s"}`);
  }
  if (backlogItem.value) {
    backlogItem.value = await api.get<QCBacklogItemOut>(`/qc/backlog/${backlogItem.value.id}`);
  }
}

async function uploadCsv(options: UploadRequestOptions) {
  try {
    const formData = new FormData();
    formData.append("file", options.file);
    const response = await api.upload<CsvIngestResult>("/qc/records/csv", formData);
    uploadSummary.value = `Accepted: ${response.accepted}, Quarantined: ${response.quarantined}, Errors: ${response.errors.length}`;
    ElMessage.success("CSV processed");
  } catch (error) {
    const message = error instanceof Error && error.message ? error.message : "CSV upload failed";
    ElMessage.error(message);
  }
}

watch(selectedStreamId, (streamId) => {
  void loadChartContext(streamId);
});

onMounted(async () => {
  const recent = readManualRecent(window.localStorage);
  if (recent) {
    common.run_id = typeof recent.run_id === "string" ? recent.run_id : common.run_id;
    common.operator_id = typeof recent.operator_id === "string" ? recent.operator_id : "";
    common.reagent_lot = typeof recent.reagent_lot === "string" ? recent.reagent_lot : "";
    common.calibration_status = typeof recent.calibration_status === "string" ? recent.calibration_status : "ok";
    selectedStreamId.value = typeof recent.stream_id === "string" ? recent.stream_id : selectedStreamId.value;
  }
  await loadStreams();
  await loadBacklogHandoff();
  await loadChartContext(selectedStreamId.value);
});
</script>
