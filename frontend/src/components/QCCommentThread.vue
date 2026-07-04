<template>
  <section class="comment-thread">
    <div class="comment-thread__header">
      <div>
        <h3>{{ title }}</h3>
        <div class="muted small-text">{{ targetLabel }}</div>
      </div>
      <el-button size="small" @click="loadComments">Refresh</el-button>
    </div>

    <div v-if="loadError" class="comment-thread__notice">
      {{ loadError }}
    </div>

    <div v-if="!loadError && comments.length" class="comment-thread__list">
      <article v-for="comment in comments" :key="comment.id" class="comment-thread__item">
        <div class="comment-thread__meta">
          <span>{{ formatDateTime(comment.created_at) }}</span>
          <span>{{ comment.actor_role ?? "unknown" }}</span>
          <span>Key #{{ comment.api_key_id ?? "unknown" }}</span>
        </div>
        <p>{{ comment.body }}</p>
      </article>
    </div>
    <el-empty v-else-if="!loading && !loadError" description="No comments" :image-size="56" />

    <div v-if="canIngestQc && !readOnly && !loadError" class="comment-thread__form">
      <el-input v-model="draft" type="textarea" :rows="3" placeholder="Add comment" />
      <div class="comment-thread__actions">
        <el-button type="primary" :loading="saving" :disabled="!canSave" @click="saveComment">
          Add Comment
        </el-button>
      </div>
    </div>
    <div v-else-if="!loadError" class="muted small-text">Current role can read comments only.</div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { api } from "../api/client";
import type { QCCommentIn, QCCommentOut, QCCommentTargetType } from "../api/contracts";
import { canIngestQc } from "../api/session";

const props = withDefaults(
  defineProps<{
    targetType: QCCommentTargetType;
    targetId: string;
    streamId?: string | null;
    title?: string;
    readOnly?: boolean;
  }>(),
  {
    title: "Comments",
    streamId: null,
    readOnly: false,
  }
);

const comments = ref<QCCommentOut[]>([]);
const draft = ref("");
const loading = ref(false);
const loadError = ref("");
const saving = ref(false);

const targetLabel = computed(() => `${props.targetType.replaceAll("_", " ")} ${props.targetId}`);
const canSave = computed(() => props.targetId.trim().length > 0 && draft.value.trim().length > 0 && !saving.value);

function formatDateTime(value: string): string {
  return new Date(value).toLocaleString();
}

function commentsPath(): string {
  const params = new URLSearchParams({
    target_type: props.targetType,
    target_id: props.targetId,
  });
  return `/qc/comments?${params.toString()}`;
}

async function loadComments(): Promise<void> {
  if (!props.targetId.trim()) {
    comments.value = [];
    loadError.value = "";
    return;
  }
  loading.value = true;
  try {
    comments.value = await api.get<QCCommentOut[]>(commentsPath());
    loadError.value = "";
  } catch (error) {
    comments.value = [];
    const message = error instanceof Error && error.message ? error.message : "";
    loadError.value = message === "Not Found"
      ? "Comments are unavailable from the current API."
      : "Comments could not be loaded.";
  } finally {
    loading.value = false;
  }
}

async function saveComment(): Promise<void> {
  const body = draft.value.trim();
  if (!body) {
    return;
  }
  saving.value = true;
  try {
    const payload: QCCommentIn = {
      target_type: props.targetType,
      target_id: props.targetId,
      stream_id: props.streamId ?? null,
      body,
    };
    const saved = await api.post<QCCommentOut>("/qc/comments", payload);
    comments.value = [...comments.value, saved];
    draft.value = "";
    ElMessage.success("Comment added");
  } catch (error) {
    const message = error instanceof Error && error.message ? error.message : "Failed to add comment";
    ElMessage.error(message);
  } finally {
    saving.value = false;
  }
}

watch(
  () => [props.targetType, props.targetId],
  () => {
    void loadComments();
  }
);

onMounted(loadComments);
</script>

<style scoped>
.comment-thread {
  display: grid;
  gap: 12px;
}

.comment-thread__header,
.comment-thread__actions,
.comment-thread__meta {
  align-items: center;
  display: flex;
  gap: 10px;
  justify-content: space-between;
  min-width: 0;
}

.comment-thread__header h3 {
  font-size: 16px;
  line-height: 1.2;
  margin: 0 0 2px;
}

.comment-thread__list {
  display: grid;
  gap: 8px;
  max-height: 240px;
  overflow: auto;
}

.comment-thread__item {
  background: #f8fafc;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  padding: 10px;
}

.comment-thread__item p {
  margin: 6px 0 0;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}

.comment-thread__meta {
  color: #64748b;
  font-size: 12px;
  justify-content: flex-start;
}

.comment-thread__form {
  display: grid;
  gap: 8px;
}

.comment-thread__notice {
  background: #fff7ed;
  border: 1px solid #fed7aa;
  border-radius: 6px;
  color: #9a3412;
  font-size: 13px;
  padding: 10px;
}
</style>
