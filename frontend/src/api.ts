const base = (
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000"
).replace(/\/$/, "");

export const API_BASE = base;
export const WS_BASE = base.replace(/^http/, "ws");

// The admin key lives in this tab only. The backend gate is optional
// (ADMIN_API_KEY), so an unset key is a valid state, not an error.
const ADMIN_KEY_STORAGE = "prodos.admin_key";

export function getAdminKey(): string | null {
  return sessionStorage.getItem(ADMIN_KEY_STORAGE);
}

export function setAdminKey(value: string): void {
  if (value) sessionStorage.setItem(ADMIN_KEY_STORAGE, value);
  else sessionStorage.removeItem(ADMIN_KEY_STORAGE);
}

export type AlertStatus = "new" | "acknowledged" | "resolved";

export interface HealthResponse {
  status: string;
}

export interface AlertStats {
  window_hours: number;
  total: number;
  by_status: Record<string, number>;
  by_severity: {
    low: number;
    medium: number;
    high: number;
  };
  newest_alert_at: string | null;
}

export interface AlertOut {
  alert_id: string;
  event_id: string;
  created_at: string;
  severity: number;
  title: string;
  explanation: string;
  recommended_action: string;
  status: AlertStatus;
}

export interface SensorOut {
  sensor_id: string;
  site_id: string | null;
  name: string | null;
  location: string | null;
  channels: number[];
  last_seen_at: string | null;
  registered_at: string;
  status: "online" | "offline" | "retired";
}

export interface SiteOut {
  site_id: string;
  business_name: string | null;
  business_type: string | null;
  wifi_ssids: string[];
  known_access_points: string[];
  router_model: string | null;
  primary_language: string;
  notes: string | null;
  trust_token: string | null;
  created_at: string;
  updated_at: string;
}

export interface ChecklistOut {
  site_id: string;
  answers: Record<string, boolean | null>;
  updated_at: string;
}

export interface ScoreOut {
  site_id: string;
  computed_at: string;
  score: number;
  band: string;
  components: Record<string, number>;
  details: Record<string, unknown>;
  window_days: number;
}

export interface TrustOut {
  site_id: string;
  trust_token: string;
}

export class ApiError extends Error {
  status: number;
  body: unknown;

  constructor(status: number, body: unknown, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

function detailText(body: unknown): string {
  if (typeof body === "string") return body;
  if (!body || typeof body !== "object") return "";

  const value = (body as { detail?: unknown }).detail;
  if (typeof value === "string") return value;

  // FastAPI validation errors: [{loc: ["body", "known_access_points", 0], msg}]
  if (Array.isArray(value)) {
    return value
      .map((item) => {
        if (!item || typeof item !== "object") return "";
        const { loc, msg } = item as { loc?: unknown; msg?: unknown };
        const where = Array.isArray(loc)
          ? loc.filter((part) => part !== "body").join(".")
          : "";
        return [where, typeof msg === "string" ? msg : ""]
          .filter(Boolean)
          .join(": ");
      })
      .filter(Boolean)
      .join("; ");
  }

  return "";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  const adminKey = getAdminKey();
  if (adminKey) headers.set("X-Admin-Key", adminKey);

  const response = await fetch(`${API_BASE}${path}`, { ...init, headers });

  if (!response.ok) {
    const text = await response.text();
    let body: unknown = text;
    try {
      body = text ? JSON.parse(text) : null;
    } catch {
      // Non-JSON error body; keep the raw text.
    }
    const message =
      response.status === 401
        ? "admin key rejected"
        : `HTTP ${response.status}${detailText(body) ? `: ${detailText(body)}` : ""}`;
    throw new ApiError(response.status, body, message);
  }

  if (response.status === 204) return undefined as unknown as T;
  return (await response.json()) as T;
}

export function getJson<T>(path: string): Promise<T> {
  return request<T>(path);
}

export function postJson<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function putJson<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function patchJson<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function delJson<T>(path: string): Promise<T> {
  return request<T>(path, { method: "DELETE" });
}

export function connect(path: string): WebSocket {
  return new WebSocket(`${WS_BASE}${path}`);
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Unknown error";
}

// The API sends UTC. Postgres adds the Z suffix; SQLite (dev) drops it, so a
// zone-less value is still UTC and must be marked before Date parses it.
export function formatLocal(value: string): string {
  const hasZone = /(?:Z|[+-]\d{2}:?\d{2})$/.test(value);
  const date = new Date(hasZone ? value : `${value}Z`);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}
