import { computed, readonly, ref } from "vue";
import { api } from "./client";
import type { CurrentUserOut, EffectiveScopeOut, Permission } from "./contracts";

type WorkflowPermission = Permission
  | "comment_qc"
  | "resolve_qc"
  | "manage_alerts"
  | "manage_investigations"
  | "manage_capas";

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

export function hasPermission(permission: WorkflowPermission): boolean {
  return (currentUser.value?.permissions as readonly string[] | undefined)?.includes(permission) ?? false;
}

export function currentEffectiveScope(): EffectiveScopeOut | null {
  return currentUser.value?.effective_scope ?? null;
}

export function defaultScopeFilter(key: "lab_benches" | "assignment_groups" | "sites"): string {
  const values = currentEffectiveScope()?.[key] ?? [];
  return values.length === 1 ? values[0] : "";
}

export const canIngestQc = computed(() => hasPermission("ingest_qc"));
export const canEditConfig = computed(() => hasPermission("edit_config"));
export const canManageImports = computed(() => hasPermission("manage_imports"));
export const canApprove = computed(() => hasPermission("approve"));
export const canCommentQc = computed(() => hasPermission("comment_qc"));
export const canResolveQc = computed(() => hasPermission("resolve_qc"));
export const canManageAlerts = computed(() => hasPermission("manage_alerts"));
export const canManageInvestigations = computed(() => hasPermission("manage_investigations"));
export const canManageCapas = computed(() => hasPermission("manage_capas"));
