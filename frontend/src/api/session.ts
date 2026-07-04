import { computed, readonly, ref } from "vue";
import { api } from "./client";
import type { CurrentUserOut, Permission } from "./contracts";

const currentUser = ref<CurrentUserOut | null>(null);

export const sessionUser = readonly(currentUser);

export async function loadSessionUser(): Promise<CurrentUserOut> {
  const user = await api.get<CurrentUserOut>("/me");
  currentUser.value = user;
  return user;
}

export function clearSessionUser(): void {
  currentUser.value = null;
}

export function hasPermission(permission: Permission): boolean {
  return currentUser.value?.permissions.includes(permission) ?? false;
}

export const canIngestQc = computed(() => hasPermission("ingest_qc"));
export const canEditConfig = computed(() => hasPermission("edit_config"));
export const canManageImports = computed(() => hasPermission("manage_imports"));
export const canApprove = computed(() => hasPermission("approve"));
