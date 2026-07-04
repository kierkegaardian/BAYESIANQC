<template>
  <div class="page kiosk-builder">
    <div class="page-header">
      <div>
        <h2>Kiosk Builder</h2>
        <div class="muted">Create saved layouts and assign chart panels.</div>
      </div>
      <el-button @click="loadData">Refresh</el-button>
    </div>

    <section class="builder-grid">
      <el-card>
        <template #header>Saved Kiosks</template>
        <el-table :data="layouts" stripe class="full-width" @row-click="selectLayout">
          <el-table-column prop="label" label="Label" />
          <el-table-column prop="slug" label="Slug" />
          <el-table-column label="Panels" width="90">
            <template #default="{ row }">{{ row.panels?.length ?? 0 }}</template>
          </el-table-column>
          <el-table-column label="Actions" width="160">
            <template #default="{ row }">
              <el-button size="small" @click.stop="openKiosk(row.slug)">Open</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <el-card>
        <template #header>Create Kiosk</template>
        <el-form label-position="top">
          <el-form-item label="Label"><el-input v-model="layoutForm.label" /></el-form-item>
          <el-form-item label="Slug"><el-input v-model="layoutForm.slug" :placeholder="slugPreview" /></el-form-item>
          <el-form-item label="Site"><el-input v-model="layoutForm.site" /></el-form-item>
          <el-form-item label="Lab Bench"><el-input v-model="layoutForm.lab_bench" /></el-form-item>
          <el-button type="primary" :disabled="!canEditConfig" @click="createLayout">Create</el-button>
        </el-form>
      </el-card>
    </section>

    <el-card class="panel-card">
      <template #header>
        <div class="panel-card-header">
          <span>{{ selectedLayout ? `Panels: ${selectedLayout.label}` : "Panels" }}</span>
          <el-button v-if="selectedLayout" size="small" @click="openKiosk(selectedLayout.slug)">Open Kiosk</el-button>
        </div>
      </template>

      <div v-if="selectedLayout" class="panel-builder">
        <el-form label-position="top" class="panel-form">
          <el-form-item label="Stream">
            <el-select v-model="panelForm.stream_id" filterable class="full-width" @change="syncPanelTitle">
              <el-option v-for="stream in streams" :key="stream.stream_id" :label="streamLabel(stream)" :value="stream.stream_id" />
            </el-select>
          </el-form-item>
          <el-form-item label="Title"><el-input v-model="panelForm.title" /></el-form-item>
          <el-form-item label="Mode">
            <el-select v-model="panelForm.mode" class="full-width">
              <el-option label="Results and risk" value="both" />
              <el-option label="Results" value="results" />
              <el-option label="Risk" value="risk" />
            </el-select>
          </el-form-item>
          <el-form-item label="Start"><el-input v-model="panelForm.start" placeholder="YYYY-MM-DD" /></el-form-item>
          <el-form-item label="End"><el-input v-model="panelForm.end" placeholder="YYYY-MM-DD" /></el-form-item>
          <el-form-item label="Window Label"><el-input v-model="panelForm.window_label" /></el-form-item>
          <el-button type="primary" :disabled="!canEditConfig" @click="appendPanel">Add Panel</el-button>
        </el-form>

        <el-table :data="selectedLayout.panels ?? []" stripe class="full-width">
          <el-table-column prop="display_order" label="#" width="70" />
          <el-table-column prop="title" label="Title" />
          <el-table-column prop="stream_id" label="Stream" />
          <el-table-column prop="mode" label="Mode" width="100" />
          <el-table-column prop="window_label" label="Window" />
        </el-table>
      </div>
      <el-empty v-else description="Select or create a kiosk." />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { api } from "../api/client";
import { canEditConfig } from "../api/session";
import type { KioskLayoutOut, StreamConfigOut } from "../api/contracts";

type ChartMode = "results" | "risk" | "both";

const layouts = ref<KioskLayoutOut[]>([]);
const streams = ref<StreamConfigOut[]>([]);
const selectedSlug = ref("");
const layoutForm = reactive({ label: "", slug: "", site: "", lab_bench: "" });
const panelForm = reactive({
  stream_id: "",
  title: "",
  mode: "both" as ChartMode,
  start: "",
  end: "",
  window_label: "",
});

const selectedLayout = computed(() => layouts.value.find((layout) => layout.slug === selectedSlug.value) ?? null);
const slugPreview = computed(() => slugify(layoutForm.label));

function slugify(value: string): string {
  return value.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

function optional(value: string): string | null {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function streamLabel(stream: StreamConfigOut): string {
  return `${stream.stream_id} - ${stream.analyte} / ${stream.instrument}`;
}

function selectLayout(layout: KioskLayoutOut): void {
  selectedSlug.value = layout.slug;
}

function openKiosk(slug: string): void {
  window.location.href = `/kiosk/${slug}`;
}

async function loadData(): Promise<void> {
  const [kioskRows, streamRows] = await Promise.all([
    api.get<KioskLayoutOut[]>("/kiosks?active=true"),
    api.get<StreamConfigOut[]>("/streams"),
  ]);
  layouts.value = kioskRows;
  streams.value = streamRows;
  if (!selectedSlug.value && kioskRows.length) {
    selectedSlug.value = kioskRows[0].slug;
  }
}

async function createLayout(): Promise<void> {
  const slug = optional(layoutForm.slug) ?? slugPreview.value;
  if (!slug || !layoutForm.label.trim()) {
    ElMessage.error("Label and slug are required");
    return;
  }
  const created = await api.post<KioskLayoutOut>("/kiosks", {
    active: true,
    slug,
    label: layoutForm.label.trim(),
    site: optional(layoutForm.site),
    lab_bench: optional(layoutForm.lab_bench),
  });
  layouts.value = [...layouts.value, created].sort((left, right) => left.label.localeCompare(right.label));
  selectedSlug.value = created.slug;
  Object.assign(layoutForm, { label: "", slug: "", site: "", lab_bench: "" });
  ElMessage.success("Kiosk created");
}

function syncPanelTitle(): void {
  if (panelForm.title.trim()) {
    return;
  }
  const stream = streams.value.find((item) => item.stream_id === panelForm.stream_id);
  if (stream) {
    panelForm.title = `${stream.analyte} - ${stream.instrument}`;
    panelForm.window_label = panelForm.window_label || "Current window";
  }
}

async function appendPanel(): Promise<void> {
  if (!selectedLayout.value || !panelForm.stream_id || !panelForm.title.trim()) {
    ElMessage.error("Kiosk, stream, and title are required");
    return;
  }
  const updated = await api.post<KioskLayoutOut>(`/kiosks/${selectedLayout.value.slug}/panels`, {
    active: true,
    stream_id: panelForm.stream_id,
    title: panelForm.title.trim(),
    mode: panelForm.mode,
    start: optional(panelForm.start),
    end: optional(panelForm.end),
    window_label: optional(panelForm.window_label),
    display_order: null,
  });
  layouts.value = layouts.value.map((layout) => (layout.slug === updated.slug ? updated : layout));
  Object.assign(panelForm, { stream_id: "", title: "", mode: "both", start: "", end: "", window_label: "" });
  ElMessage.success("Panel added");
}

onMounted(loadData);
</script>

<style scoped>
.kiosk-builder { max-width: 1240px; }
.builder-grid { display: grid; gap: 16px; grid-template-columns: minmax(0, 2fr) minmax(320px, 1fr); }
.panel-card { margin-top: 16px; }
.panel-card-header { align-items: center; display: flex; justify-content: space-between; }
.panel-builder { display: grid; gap: 16px; grid-template-columns: 340px minmax(0, 1fr); }
.panel-form { border-right: 1px solid #e5e7eb; padding-right: 16px; }
@media (max-width: 980px) {
  .builder-grid, .panel-builder { grid-template-columns: 1fr; }
  .panel-form { border-right: 0; padding-right: 0; }
}
</style>
