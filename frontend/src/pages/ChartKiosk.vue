<template>
  <main class="kiosk-screen">
    <header class="kiosk-header">
      <div class="kiosk-title">
        <div class="kiosk-label">
          {{ kioskLabel }}
          <span v-if="isStakeholderDeployment" class="demo-notice">Synthetic stakeholder demonstration — not validated for laboratory use</span>
        </div>
        <h1>{{ headerTitle }}</h1>
        <div class="kiosk-meta">
          {{ headerMeta }}
        </div>
      </div>
      <div class="kiosk-header-right">
        <ChartRiskBadge v-if="isSingleView" :summary="riskSummary" kiosk />
        <el-button v-if="isSingleView" size="small" @click="openGridView">Back to overview</el-button>
        <el-button v-if="isSingleView" size="small" @click="advancePanel">Next stream</el-button>
        <el-button size="small" :disabled="interactionKeys.size > 0" @click="togglePause">
          {{ interactionKeys.size > 0 ? "Paused for review" : manualPaused ? "Resume" : "Pause" }}
        </el-button>
        <div class="kiosk-status" aria-live="polite">
          <span>{{ positionLabel }}</span>
          <span>{{ paused ? "Paused" : `${secondsRemaining}s` }}</span>
          <span>{{ lastRefreshLabel }}</span>
        </div>
      </div>
    </header>

    <ChartView
      v-if="isSingleView && activePanel"
      kiosk
      :forced-stream-id="activePanel.streamId"
      :forced-start="activePanel.start"
      :forced-end="activePanel.end"
      :forced-mode="mode"
      :refresh-token="refreshToken"
      @risk-summary="updateRiskSummary"
      @interaction-active="setPanelInteraction(activePanel.streamId, $event)"
    />

    <div
      v-else-if="visiblePanels.length"
      class="kiosk-grid"
      :class="{ 'kiosk-grid--single': visiblePanels.length === 1 }"
    >
      <KioskChartTile
        v-for="panel in visiblePanels"
        :key="panel.streamId"
        :panel="panel"
        :mode="mode"
        :refresh-token="refreshToken"
        @open-single="openSingleStream"
        @interaction-active="setPanelInteraction(panel.streamId, $event)"
      />
    </div>
    <div v-else class="kiosk-empty">
      {{ kioskError || "No chart panels are assigned to this kiosk." }}
    </div>
  </main>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { api } from "../api/client";
import type { KioskLayoutOut } from "../api/contracts";
import { loadSessionUser } from "../api/session";
import { isStakeholderDeployment } from "../deployment";
import ChartRiskBadge from "./ChartRiskBadge.vue";
import ChartView from "./ChartView.vue";
import KioskChartTile from "./KioskChartTile.vue";
import type { ChartRiskSummary } from "./chartRisk";
import { kioskLayoutForPath, staticKioskLayoutForPath, type KioskLayout, type KioskPanel } from "./kioskPanels";
import {
  normalizeInterval,
  normalizeMode,
  normalizeTileCount,
  normalizeView,
  queryValue,
  requestedStreamIds,
  type ChartMode,
} from "./kioskRuntime";

const route = useRoute();
const router = useRouter();
const activeIndex = ref(0);
const activePage = ref(0);
const secondsRemaining = ref(20);
const refreshToken = ref(0);
const lastRefreshAt = ref(new Date());
const riskSummary = ref<ChartRiskSummary | null>(null);
const savedLayout = ref<KioskLayout | null>(null);
const kioskError = ref("");
const manualPaused = ref(false);
const interactionKeys = ref(new Set<string>());
const paused = computed(() => manualPaused.value || interactionKeys.value.size > 0);
let ticker: number | null = null;

const mode = computed<ChartMode>(() => normalizeMode(route.query.mode));
const intervalSeconds = computed(() => normalizeInterval(route.query.interval));
const viewMode = computed(() => normalizeView(route.query.view));
const isSingleView = computed(() => viewMode.value === "single");
const tileCount = computed(() => normalizeTileCount(route.query.tiles));
const staticLayout = computed(() => staticKioskLayoutForPath(route.path));
const kioskLayout = computed(() => savedLayout.value ?? staticLayout.value ?? kioskLayoutForPath(route.path));
const kioskLabel = computed(() => kioskLayout.value.label);
const presetPanels = computed<KioskPanel[]>(() => kioskLayout.value.panels);
const panels = computed(() => {
  const requested = requestedStreamIds(route.query.streams);
  if (!requested) {
    return presetPanels.value;
  }
  const filtered = presetPanels.value.filter((panel) => requested.has(panel.streamId));
  return filtered.length ? filtered : presetPanels.value;
});
const activePanel = computed<KioskPanel | null>(() => panels.value[activeIndex.value] ?? panels.value[0] ?? null);
const pageCount = computed(() =>
  Math.max(1, Math.ceil(panels.value.length / tileCount.value))
);
const visiblePanels = computed(() => {
  const start = activePage.value * tileCount.value;
  return panels.value.slice(start, start + tileCount.value);
});
const headerTitle = computed(() =>
  isSingleView.value ? activePanel.value?.title ?? "Saved kiosk" : "Multi-chart QC overview"
);
const headerMeta = computed(() => {
  if (!panels.value.length) {
    return kioskError.value || "No assigned streams";
  }
  if (isSingleView.value) {
    return `${activePanel.value?.streamId ?? ""} · ${activePanel.value?.windowLabel ?? ""}`;
  }
  const first = activePage.value * tileCount.value + 1;
  const last = Math.min(first + visiblePanels.value.length - 1, panels.value.length);
  return `${first}-${last} of ${panels.value.length} streams · ${mode.value} mode`;
});
const positionLabel = computed(() => {
  if (!panels.value.length) {
    return "0 / 0";
  }
  return isSingleView.value
    ? `${activeIndex.value + 1} / ${panels.value.length}`
    : `${activePage.value + 1} / ${pageCount.value}`;
});
const lastRefreshLabel = computed(() =>
  lastRefreshAt.value.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  })
);

function resetCountdown(): void {
  secondsRemaining.value = intervalSeconds.value;
}

function refreshPanel(): void {
  riskSummary.value = null;
  refreshToken.value += 1;
  lastRefreshAt.value = new Date();
}

function advancePanel(): void {
  if (!panels.value.length) {
    resetCountdown();
    return;
  }
  if (isSingleView.value) {
    activeIndex.value = (activeIndex.value + 1) % panels.value.length;
  } else {
    activePage.value = (activePage.value + 1) % pageCount.value;
  }
  resetCountdown();
  refreshPanel();
}

function syncRequestedPanel(): void {
  if (!panels.value.length) {
    activeIndex.value = 0;
    activePage.value = 0;
    return;
  }
  const requested = queryValue(route.query.stream);
  if (!requested) {
    activeIndex.value = Math.min(activeIndex.value, panels.value.length - 1);
    activePage.value = Math.min(activePage.value, pageCount.value - 1);
    return;
  }
  const requestedIndex = panels.value.findIndex((panel) => panel.streamId === requested);
  if (requestedIndex >= 0) {
    activeIndex.value = requestedIndex;
    activePage.value = Math.floor(requestedIndex / tileCount.value);
  }
}

function startTicker(): void {
  if (ticker !== null) {
    window.clearInterval(ticker);
  }
  resetCountdown();
  ticker = window.setInterval(() => {
    if (paused.value) {
      return;
    }
    secondsRemaining.value -= 1;
    if (secondsRemaining.value <= 0) {
      advancePanel();
    }
  }, 1000);
}

function updateRiskSummary(summary: ChartRiskSummary | null): void {
  riskSummary.value = summary;
}

function togglePause(): void {
  manualPaused.value = !manualPaused.value;
  if (!manualPaused.value) resetCountdown();
}

function setPanelInteraction(streamId: string, active: boolean): void {
  const next = new Set(interactionKeys.value);
  if (active) next.add(streamId); else next.delete(streamId);
  interactionKeys.value = next;
}

function openSingleStream(streamId: string): void {
  manualPaused.value = true;
  void router.push({
    path: route.path,
    query: { ...route.query, view: "single", stream: streamId },
  });
}

function openGridView(): void {
  manualPaused.value = false;
  interactionKeys.value = new Set();
  void router.push({
    path: route.path,
    query: { ...route.query, view: "grid", stream: undefined },
  });
}

function savedLayoutToKioskLayout(layout: KioskLayoutOut): KioskLayout {
  return {
    label: layout.label,
    panels: (layout.panels ?? [])
      .filter((panel) => panel.active)
      .sort((left, right) => left.display_order - right.display_order)
      .map((panel) => ({
        streamId: panel.stream_id,
        title: panel.title,
        start: panel.start ?? "",
        end: panel.end ?? "",
        windowLabel: panel.window_label ?? "Current window",
      })),
  };
}

async function loadSavedLayout(): Promise<void> {
  kioskError.value = "";
  savedLayout.value = null;
  if (staticLayout.value) {
    return;
  }
  const slug = typeof route.params.slug === "string" ? route.params.slug : "";
  if (!slug) {
    kioskError.value = "Missing kiosk slug.";
    return;
  }
  try {
    savedLayout.value = savedLayoutToKioskLayout(await api.get<KioskLayoutOut>(`/kiosks/${slug}`));
  } catch (error) {
    kioskError.value = error instanceof Error ? error.message : "Failed to load kiosk layout.";
  }
}

watch(
  () => [
    panels.value.map((panel) => panel.streamId).join(","),
    route.query.stream,
    tileCount.value,
    viewMode.value,
  ],
  () => {
    syncRequestedPanel();
    resetCountdown();
    refreshPanel();
  },
  { immediate: true }
);

watch(intervalSeconds, () => {
  startTicker();
});

watch(
  viewMode,
  (view) => {
    manualPaused.value = view === "single";
  },
  { immediate: true }
);

watch(
  () => route.path,
  () => {
    void loadSavedLayout();
    syncRequestedPanel();
    resetCountdown();
    refreshPanel();
  },
  { immediate: true }
);

onMounted(() => {
  void loadSessionUser().catch(() => undefined);
  startTicker();
});

onBeforeUnmount(() => {
  if (ticker !== null) {
    window.clearInterval(ticker);
    ticker = null;
  }
});
</script>

<style scoped>
.kiosk-screen {
  background: #111827;
  color: #f8fafc;
  min-height: 100vh;
  overflow: hidden;
}

.kiosk-header {
  align-items: center;
  background: #1f2937;
  border-bottom: 4px solid #14b8a6;
  display: flex;
  gap: 24px;
  justify-content: space-between;
  min-height: 92px;
  padding: 16px 24px;
}

.kiosk-title { min-width: 0; }

.kiosk-label {
  color: #f59e0b;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0;
  text-transform: uppercase;
}

.demo-notice {
  background: #78350f;
  border: 1px solid #f59e0b;
  border-radius: 999px;
  color: #fef3c7;
  display: inline-block;
  margin-left: 8px;
  padding: 2px 8px;
}

h1 {
  font-size: 32px;
  letter-spacing: 0;
  line-height: 1.1;
  margin: 2px 0;
}

.kiosk-meta { color: #cbd5e1; font-size: 15px; }

.kiosk-status {
  align-items: center;
  color: #e5e7eb;
  display: flex;
  font-variant-numeric: tabular-nums;
  gap: 12px;
  white-space: nowrap;
}

.kiosk-header-right {
  align-items: center;
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  justify-content: flex-end;
}

.kiosk-status span {
  background: #0f172a;
  border: 1px solid #475569;
  min-width: 72px;
  padding: 8px 10px;
  text-align: center;
}

.kiosk-grid {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  grid-auto-rows: minmax(0, 1fr);
  height: calc(100vh - 92px);
  padding: 12px;
}

.kiosk-grid--single { grid-template-columns: minmax(0, 1fr); }

.kiosk-empty {
  align-items: center;
  color: #e2e8f0;
  display: flex;
  font-size: 22px;
  justify-content: center;
  min-height: calc(100vh - 96px);
  text-align: center;
}

@media (max-width: 760px) {
  .kiosk-header {
    align-items: flex-start;
    flex-direction: column;
    gap: 12px;
  }

  h1 { font-size: 24px; }

  .kiosk-status { flex-wrap: wrap; }

  .kiosk-header-right { justify-content: flex-start; }

  .kiosk-screen { overflow: visible; }

  .kiosk-grid {
    grid-template-columns: minmax(0, 1fr);
    height: auto;
    overflow: visible;
  }
}
</style>
