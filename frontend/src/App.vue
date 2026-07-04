<template>
  <router-view />
  <HelpButton v-if="showHelp" />
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useRoute } from "vue-router";
import HelpButton from "./components/HelpButton.vue";

const route = useRoute();
const showHelp = computed(() => route.meta.hideHelp !== true);
</script>
