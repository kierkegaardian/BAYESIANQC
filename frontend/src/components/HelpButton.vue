<template>
  <div class="help-anchor">
    <el-button type="primary" circle @click="open = true">?</el-button>
  </div>
  <el-dialog v-model="open" :title="title" width="420px">
    <p>{{ helpText }}</p>
    <template #footer>
      <el-button type="primary" @click="open = false">Got it</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import { useRoute } from "vue-router";

const route = useRoute();
const open = ref(false);

const title = computed(() => (route.meta?.helpTitle as string) || "Help");
const helpText = computed(
  () =>
    (route.meta?.helpText as string) ||
    "This page provides tools for managing BayesianQC data. Use the navigation menu to explore."
);
</script>

<style scoped>
.help-anchor {
  position: fixed;
  right: 20px;
  bottom: 20px;
  z-index: 2000;
}
</style>
