import { useEffect, useState } from "react";

const API_BASE = (
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000"
).replace(/\/$/, "");

type BackendStatus = "checking" | "online" | "offline";
type AlertStatus = "new" | "acknowledged" | "resolved";

interface HealthResponse {
  status: string;
}

interface AlertStats {
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

interface AlertOut {
  alert_id: string;
  event_id: string;
  created_at: string;
  severity: number;
  title: string;
  explanation: string;
  recommended_action: string;
  status: AlertStatus;
}

interface SensorOut {
  sensor_id: string;
  name: string | null;
  location: string | null;
  channels: number[];
  last_seen_at: string | null;
  registered_at: string;
  status: "online" | "offline" | "retired";
}

interface FrameOut {
  id: number;
  sensor_id: string;
  received_at: string;
  batch_seq: number;
  channel: number;
  frame_type: string;
  src_mac: string;
  dst_mac: string;
  bssid: string | null;
  ssid: string | null;
  rssi: number;
  seq_num: number | null;
}

type FetchResult<T> =
  | { ok: true; value: T }
  | { ok: false; error: unknown };

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`);

  if (!response.ok) {
    const body = await response.text();
    throw new Error(
      `HTTP ${response.status}${body ? `: ${body}` : ""}`,
    );
  }

  return (await response.json()) as T;
}

async function settle<T>(request: Promise<T>): Promise<FetchResult<T>> {
  try {
    return { ok: true, value: await request };
  } catch (error) {
    return { ok: false, error };
  }
}

function severityClass(severity: number): string {
  if (severity >= 8) return "sev-high";
  if (severity >= 4) return "sev-medium";
  return "sev-low";
}

function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Unknown error";
}

export default function App() {
  const [backendStatus, setBackendStatus] =
    useState<BackendStatus>("checking");
  const [stats, setStats] = useState<AlertStats | null>(null);
  const [sensors, setSensors] = useState<SensorOut[] | null>(null);
  const [frames, setFrames] = useState<FrameOut[] | null>(null);
  const [coreError, setCoreError] = useState<string | null>(null);
  const [lastChecked, setLastChecked] = useState<string | null>(null);

  const [alerts, setAlerts] = useState<AlertOut[] | null>(null);
  const [alertsLoading, setAlertsLoading] = useState(true);
  const [alertsError, setAlertsError] = useState<string | null>(null);
  const [alertsRetry, setAlertsRetry] = useState(0);

  useEffect(() => {
    let cancelled = false;

    const refreshDashboard = async () => {
      const [healthResult, statsResult, sensorsResult, framesResult] =
        await Promise.all([
          settle(getJson<HealthResponse>("/health")),
          settle(getJson<AlertStats>("/alerts/stats")),
          settle(getJson<SensorOut[]>("/sensors")),
          settle(getJson<FrameOut[]>("/frames/recent?limit=5")),
        ]);

      if (cancelled) return;

      const failures: string[] = [];

      if (healthResult.ok && healthResult.value.status === "ok") {
        setBackendStatus("online");
      } else {
        setBackendStatus("offline");
        failures.push("backend health");
      }

      if (statsResult.ok) {
        setStats(statsResult.value);
      } else {
        failures.push("alert statistics");
      }

      if (sensorsResult.ok) {
        setSensors(sensorsResult.value);
      } else {
        failures.push("sensors");
      }

      if (framesResult.ok) {
        setFrames(framesResult.value);
      } else {
        failures.push("recent frames");
      }

      setCoreError(
        failures.length > 0
          ? `Some data could not be loaded: ${failures.join(", ")}.`
          : null,
      );
      setLastChecked(new Date().toLocaleTimeString());
    };

    void refreshDashboard();
    const intervalId = window.setInterval(() => {
      void refreshDashboard();
    }, 15000);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    const loadAlerts = async () => {
      try {
        const items = await getJson<AlertOut[]>("/alerts?limit=5");
        if (!cancelled) {
          setAlerts(items);
          setAlertsError(null);
        }
      } catch (error) {
        if (!cancelled) {
          setAlertsError(errorMessage(error));
        }
      } finally {
        if (!cancelled) {
          setAlertsLoading(false);
        }
      }
    };

    void loadAlerts();

    return () => {
      cancelled = true;
    };
  }, [alertsRetry]);

  const backendLabel =
    backendStatus === "checking"
      ? "Checking"
      : backendStatus === "online"
        ? "Online"
        : "Offline";

  const onlineSensors =
    sensors === null
      ? "—"
      : sensors.filter((sensor) => sensor.status === "online").length;

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">PRODOS</div>
        <div className="nav-item active">Dashboard</div>
        <div className="nav-item">Sensors</div>
        <div className="nav-item">Alerts</div>
        <div className="nav-item">Settings</div>
      </aside>

      <header className="header">
        <h1>Security Dashboard</h1>
        <span className={`status-pill status-${backendStatus}`}>
          <span aria-hidden="true">●</span> Backend {backendLabel}
        </span>
      </header>

      <main className="main">
        {coreError && (
          <div className="error-banner" role="alert">
            {coreError} Automatic refresh runs every 15 seconds.
          </div>
        )}

        <div className="state-message">
          {lastChecked
            ? `Last checked: ${lastChecked}`
            : "Connecting to the backend…"}
        </div>

        <div className="stat-grid">
          <div className="card">
            <h3>Total Alerts (24h)</h3>
            <div className="value">{stats ? stats.total : "—"}</div>
          </div>

          <div className="card">
            <h3>High Severity (24h)</h3>
            <div className="value danger">
              {stats ? stats.by_severity.high : "—"}
            </div>
          </div>

          <div className="card">
            <h3>Connected Sensors</h3>
            <div className="value ok">{onlineSensors}</div>
          </div>

          <div className="card">
            <h3>Backend API</h3>
            <div
              className={`value ${
                backendStatus === "online"
                  ? "ok"
                  : backendStatus === "offline"
                    ? "danger"
                    : ""
              }`}
            >
              {backendLabel}
            </div>
          </div>
        </div>

        <div className="section-heading">
          <div className="section-title">Recent Security Alerts</div>
          {alertsError && (
            <button
              className="retry-button"
              onClick={() => {
                setAlertsError(null);
                setAlertsLoading(true);
                setAlertsRetry((retry) => retry + 1);
              }}
              disabled={alertsLoading}
            >
              Retry
            </button>
          )}
        </div>

        {alertsError && (
          <div className="error-banner" role="alert">
            <div>Could not load /alerts: {alertsError}</div>
            {alertsError.startsWith("HTTP 500") && (
              <p>
                The local backend trace showed a SQLite migration issue with
                alerts.lang. This needs a backend fix; it is not an empty alert
                list.
              </p>
            )}
          </div>
        )}

        <div className="card">
          {alertsLoading && (
            <div className="state-message">Loading alerts…</div>
          )}

          {!alertsLoading && !alertsError && alerts?.length === 0 && (
            <div className="state-message">
              No alerts have been returned by the backend.
            </div>
          )}

          {alerts?.map((alert) => (
            <div className="alert-row" key={alert.alert_id}>
              <div className="alert-title">
                {alert.title}{" "}
                <span
                  className={`sev-badge ${severityClass(alert.severity)}`}
                >
                  SEV {alert.severity}
                </span>
              </div>
              <div className="alert-meta">
                {formatDate(alert.created_at)} · {alert.status}
              </div>
              <div className="alert-meta">{alert.explanation}</div>
              <div className="alert-action">
                <strong>Suggested action:</strong>{" "}
                {alert.recommended_action}
              </div>
            </div>
          ))}
        </div>

        <div className="section-title">Recent Network Frames</div>
        <div className="card">
          {frames === null && (
            <div className="state-message">
              Waiting for frame data from the backend…
            </div>
          )}

          {frames?.length === 0 && (
            <div className="state-message">
              No recent frames. Check that the MQTT broker and a sensor are
              running.
            </div>
          )}

          {frames?.map((frame) => (
            <div className="live-row" key={frame.id}>
              <span>{frame.frame_type}</span>
              <span>{frame.src_mac}</span>
              <span>{frame.sensor_id}</span>
              <span>
                {frame.rssi} dBm · Ch {frame.channel}
              </span>
            </div>
          ))}
        </div>
      </main>
    </div>
  );
}