<template>
  <div class="login-page">
    <el-card class="login-card">
      <h2>BayesianQC Console</h2>
      <p class="muted">
        Enter your API key to start. Default local key: <code>local-dev-key</code>.
      </p>
      <el-form label-position="top" class="login-form">
        <el-form-item label="API Key">
          <el-input v-model="apiKey" placeholder="Enter API key" show-password />
        </el-form-item>
        <el-button type="primary" class="full-width" @click="login">
          Connect
        </el-button>
      </el-form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { api, setApiKey } from "../api/client";

const router = useRouter();
const apiKey = ref("local-dev-key");

async function login() {
  try {
    setApiKey(apiKey.value.trim());
    await api.get("/reports/summary");
    ElMessage.success("Connected to API");
    router.push("/");
  } catch (error) {
    ElMessage.error("Could not connect. Check your API key and server.");
  }
}
</script>

<style scoped>
.login-page {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  background: radial-gradient(circle at top, #e0f2fe, #f8fafc);
}

.login-card {
  width: 420px;
}

.login-form {
  margin-top: 16px;
}
</style>
