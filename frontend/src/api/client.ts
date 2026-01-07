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

export function getApiKey(): string | null {
  return window.localStorage.getItem(API_KEY_STORAGE);
}

export function setApiKey(key: string): void {
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
    throw new Error(message || `Request failed with ${response.status}`);
  }
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return response.json() as Promise<T>;
  }
  return response.text() as unknown as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown, headers?: HeadersInit) =>
    request<T>(path, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...(headers || {}) },
      body: body ? JSON.stringify(body) : undefined,
    }),
  patch: <T>(path: string, body?: unknown, headers?: HeadersInit) =>
    request<T>(path, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", ...(headers || {}) },
      body: body ? JSON.stringify(body) : undefined,
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
