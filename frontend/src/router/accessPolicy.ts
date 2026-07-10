export type StakeholderRouteContext = {
  stakeholderDeployment: boolean;
  path: string;
  stakeholderVisible: boolean;
};

export function stakeholderRedirect(context: StakeholderRouteContext): string | null {
  if (!context.stakeholderDeployment || context.path === "/login") return null;
  return context.stakeholderVisible ? null : "/";
}
