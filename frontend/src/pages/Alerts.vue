<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2>Alerts</h2>
        <div class="muted">Review and update alert status.</div>
      </div>
      <el-button @click="loadAlerts">Refresh</el-button>
    </div>

    <el-table :data="alerts" stripe class="full-width">
      <el-table-column prop="id" label="Alert ID" />
      <el-table-column prop="stream_id" label="Stream" />
      <el-table-column prop="disposition" label="Disposition" />
      <el-table-column prop="status" label="Status" />
      <el-table-column label="Assign">
        <template #default="{ row }">
          <el-input v-model="row.assigned_to" placeholder="Assignee" />
        </template>
      </el-table-column>
      <el-table-column label="Status Update" width="180">
        <template #default="{ row }">
          <el-select v-model="row.status" placeholder="Status">
            <el-option label="open" value="open" />
            <el-option label="acknowledged" value="acknowledged" />
            <el-option label="closed" value="closed" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="Actions" width="140">
        <template #default="{ row }">
          <el-button size="small" @click="saveAlert(row)">Save</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import { api } from "../api/client";

const alerts = ref<any[]>([]);

async function loadAlerts() {
  alerts.value = await api.get("/alerts");
}

async function saveAlert(row: any) {
  try {
    await api.patch(`/alerts/${row.id}`, {
      status: row.status,
      assigned_to: row.assigned_to,
      acknowledged_by: row.acknowledged_by || "ui-user",
    });
    ElMessage.success("Alert updated");
  } catch (error) {
    ElMessage.error("Failed to update alert");
  }
}

onMounted(loadAlerts);
</script>
