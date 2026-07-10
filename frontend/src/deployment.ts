export type DeploymentMode = "standard" | "stakeholder";

const configuredMode = import.meta.env.VITE_DEPLOYMENT_MODE;

export const deploymentMode: DeploymentMode =
  configuredMode === "stakeholder" ? "stakeholder" : "standard";

export const isStakeholderDeployment = deploymentMode === "stakeholder";
