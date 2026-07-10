/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL?: string;
  readonly VITE_AUTH_MODE?: string;
  readonly VITE_DEPLOYMENT_MODE?: "standard" | "stakeholder";
}
