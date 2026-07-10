<template>
  <div class="login-page">
    <el-card class="login-card">
      <h2>BayesianQC Console</h2>
      <p class="muted">Enter an API key to start. Local demos may seed <code>local-dev-key</code>.</p>
      <el-form label-position="top" class="login-form" @submit.prevent="login">
        <el-form-item label="API Key"><el-input v-model="apiKey" placeholder="Enter API key" show-password autocomplete="current-password" /></el-form-item>
        <el-button native-type="submit" type="primary" class="full-width" :loading="loading" :disabled="!apiKey.trim()">Connect</el-button>
      </el-form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { clearApiKey, setApiKey } from "../api/client";
import { clearSessionUser, loadSessionUser } from "../api/session";

const route = useRoute();
const router = useRouter();
const apiKey = ref("");
const loading = ref(false);

function redirectTarget(): string {
  const raw = Array.isArray(route.query.redirect) ? route.query.redirect[0] : route.query.redirect;
  return typeof raw === "string" && raw.startsWith("/") && !raw.startsWith("//") ? raw : "/";
}

async function login(): Promise<void> {
  if (!apiKey.value.trim() || loading.value) return;
  loading.value = true;
  try {
    setApiKey(apiKey.value.trim());
    await loadSessionUser();
    ElMessage.success("Connected to API");
    await router.push(redirectTarget());
  } catch {
    clearApiKey();
    clearSessionUser();
    ElMessage.error("Could not connect. Check your API key and server.");
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped>
.login-page { align-items: center; background: radial-gradient(circle at top, #e0f2fe, #f8fafc); display: flex; justify-content: center; min-height: 100vh; padding: 16px; }
.login-card { max-width: 420px; width: 100%; }
.login-form { margin-top: 16px; }
</style>
