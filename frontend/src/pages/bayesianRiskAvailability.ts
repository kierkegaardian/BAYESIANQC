import type { BayesianRisk } from "../api/contracts";

type RiskAvailabilityFields = {
  status?: "available" | "unavailable";
  unavailable_reason?: string | null;
  probability_outside_limits?: number | null;
  probability_outside_warning?: number | null;
  risk_score?: number | null;
  posterior_mean?: number | null;
  predictive_sigma?: number | null;
};

export type RiskMetricKey =
  | "probability_outside_limits"
  | "probability_outside_warning"
  | "risk_score"
  | "posterior_mean"
  | "predictive_sigma";

function availabilityFields(risk: BayesianRisk): RiskAvailabilityFields {
  return risk as BayesianRisk & RiskAvailabilityFields;
}

export function riskIsUnavailable(risk: BayesianRisk | null | undefined): boolean {
  return Boolean(risk && availabilityFields(risk).status === "unavailable");
}

export function availableRiskNumber(
  risk: BayesianRisk | null | undefined,
  key: RiskMetricKey
): number | null {
  if (!risk || riskIsUnavailable(risk)) return null;
  const value = availabilityFields(risk)[key];
  if (value === null || value === undefined) return null;
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

export function unavailableRiskReason(risk: BayesianRisk | null | undefined): string {
  if (!risk || !riskIsUnavailable(risk)) return "";
  const reason = availabilityFields(risk).unavailable_reason;
  if (reason === "missing_effective_prior") return "Missing effective prior";
  if (reason === "model_evaluation_failure") return "Model evaluation failed";
  return reason ? reason.replaceAll("_", " ") : "Reason unavailable";
}

export function unavailableRiskMessage(risk: BayesianRisk | null | undefined): string {
  const reason = unavailableRiskReason(risk);
  return reason ? `Bayesian inference unavailable: ${reason}.` : "Bayesian inference unavailable.";
}
