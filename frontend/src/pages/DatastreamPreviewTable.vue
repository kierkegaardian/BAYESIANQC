<template>
  <el-table :data="preview.rows" stripe class="full-width">
    <el-table-column prop="row" label="Row" width="80" />
    <el-table-column prop="stream_id" label="Stream" />
    <el-table-column label="Status" width="110">
      <template #default="{ row }">
        <el-tag :type="row.valid ? 'success' : 'danger'">{{ row.valid ? "valid" : "error" }}</el-tag>
      </template>
    </el-table-column>
    <el-table-column label="Actions">
      <template #default="{ row }">{{ actionSummary(row) }}</template>
    </el-table-column>
    <el-table-column label="Errors">
      <template #default="{ row }">{{ row.errors?.join("; ") }}</template>
    </el-table-column>
  </el-table>
</template>

<script setup lang="ts">
import type { StreamSetupPreviewOut, StreamSetupPreviewRow } from "../api/contracts";

defineProps<{
  preview: StreamSetupPreviewOut;
}>();

function actionSummary(row: StreamSetupPreviewRow): string {
  return row.actions?.map((action) => `${action.entity}:${action.action}`).join(", ") ?? "";
}
</script>
