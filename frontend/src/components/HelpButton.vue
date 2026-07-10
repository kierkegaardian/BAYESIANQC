<template>
  <div class="help-anchor">
    <el-button type="primary" circle aria-label="Open page help" @click="open = true">?</el-button>
  </div>
  <el-dialog v-model="open" :title="title" width="min(420px, calc(100vw - 32px))">
    <p>{{ helpText }}</p>
    <template #footer><el-button type="primary" @click="open = false">Got it</el-button></template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import { useRoute } from "vue-router";

const route = useRoute();
const open = ref(false);
const title = computed(() => route.meta.helpTitle ?? "Help");
const helpText = computed(() => route.meta.helpText || "Use the navigation menu to explore BayesianQC.");
</script>

<style scoped>
.help-anchor { bottom: 20px; position: fixed; right: 20px; z-index: 2000; }
</style>
