const DEFAULT_API_HOST =
  typeof window !== "undefined" && window.location.hostname
    ? window.location.hostname
    : "127.0.0.1";
const DEFAULT_API_PROTOCOL =
  typeof window !== "undefined" && window.location.protocol === "https:"
    ? "https"
    : "http";
const API_BASE =
  import.meta.env.VITE_API_URL ||
  `${DEFAULT_API_PROTOCOL}://${DEFAULT_API_HOST}:8010`;

const API_KEY_STORAGE = "bayesianqc_api_key";
const AUTH_MODE = import.meta.env.VITE_AUTH_MODE || "api-key";

export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export type PageResult<T> = {
  items: T[];
  total: number;
  limit: number;
  offset: number;
};

export function usesEdgeAuth(): boolean {
  return AUTH_MODE === "edge-basic";
}

export function getApiKey(): string | null {
  if (usesEdgeAuth()) {
    return null;
  }
  return window.localStorage.getItem(API_KEY_STORAGE);
}

export function setApiKey(key: string): void {
  if (usesEdgeAuth()) {
    return;
  }
  window.localStorage.setItem(API_KEY_STORAGE, key);
}

export function clearApiKey(): void {
  window.localStorage.removeItem(API_KEY_STORAGE);
}

function buildHeaders(extra?: HeadersInit): Headers {
  const headers = new Headers(extra || {});
  const apiKey = getApiKey();
  if (apiKey) {
    headers.set("X-API-Key", apiKey);
  }
  return headers;
}

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const { data } = await requestWithResponse<T>(path, options);
  return data;
}

async function requestWithResponse<T>(
  path: string,
  options: RequestInit = {}
): Promise<{ data: T; response: Response }> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: buildHeaders(options.headers),
  });

  if (!response.ok) {
    const text = await response.text();
    let message = text;
    if (text) {
      try {
        const parsed = JSON.parse(text) as { detail?: unknown };
        if (parsed && typeof parsed === "object" && "detail" in parsed) {
          const detail = parsed.detail;
          if (typeof detail === "string") {
            message = detail;
          } else {
            message = JSON.stringify(detail);
          }
        }
      } catch {
        // Keep raw text when it isn't JSON.
      }
    }
    throw new ApiError(message || `Request failed with ${response.status}`, response.status);
  }
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return { data: await response.json() as T, response };
  }
  return { data: await response.text() as unknown as T, response };
}

function positiveInteger(value: string | null, fallback: number): number {
  if (value === null || value.trim() === "") {
    return fallback;
  }
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed >= 0 ? parsed : fallback;
}

async function getPage<T>(path: string): Promise<PageResult<T>> {
  const { data, response } = await requestWithResponse<T[]>(path);
  const url = new URL(path, "http://local.invalid");
  const offset = positiveInteger(url.searchParams.get("offset"), 0);
  const limit = positiveInteger(url.searchParams.get("limit"), data.length);
  const total = positiveInteger(response.headers.get("X-Total-Count"), offset + data.length);
  return { items: data, total, limit, offset };
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  getPage,
  post: <T>(path: string, body?: unknown, headers?: HeadersInit) =>
    request<T>(path, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...(headers || {}) },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    }),
  patch: <T>(path: string, body?: unknown, headers?: HeadersInit) =>
    request<T>(path, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", ...(headers || {}) },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    }),
  upload: <T>(path: string, formData: FormData, headers?: HeadersInit) =>
    request<T>(path, {
      method: "POST",
      headers,
      body: formData,
    }),
};

export function getApiBase(): string {
  return API_BASE;
}
