import { useEffect, useState } from "react";
import {
  connect,
  errorMessage,
  formatLocal,
  getJson,
  patchJson,
  type AlertOut,
  type AlertStats,
  type HealthResponse,
  type SensorOut,
} from "../api";

type BackendStatus = "checking" | "online" | "offline";

type FetchResult<T> = { ok: true; value: T } | { ok: false; error: unknown };

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

function mergeAlerts(current: AlertOut[] | null, incoming: AlertOut[]): AlertOut[] {
  const byId = new Map<string, AlertOut>();
  for (const alert of [...(current ?? []), ...incoming]) {
    byId.set(alert.alert_id, alert);
  }
  return [...byId.values()]
    .sort((a, b) => b.created_at.localeCompare(a.created_at))
    .slice(0, 50);
}

export default function DashboardView() {
  const [backendStatus, setBackendStatus] =
    useState<BackendStatus>("checking");
  const [stats, setStats] = useState<AlertStats | null>(null);
  const [sensors, setSensors] = useState<SensorOut[] | null>(null);
  const [coreError, setCoreError] = useState<string | null>(null);
  const [lastChecked, setLastChecked] = useState<string | null>(null);

  const [alerts, setAlerts] = useState<AlertOut[] | null>(null);
  const [alertsLoading, setAlertsLoading] = useState(true);
  const [alertsError, setAlertsError] = useState<string | null>(null);
  const [alertsRetry, setAlertsRetry] = useState(0);
  const [pendingAlertId, setPendingAlertId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const [frameCount, setFrameCount] = useState(0);
  const [lastFrameAt, setLastFrameAt] = useState<Date | null>(null);
  const [framesConnected, setFramesConnected] = useState(false);

  useEffect(() => {
    let cancelled = false;

    const refreshDashboard = async () => {
      const [healthResult, statsResult, sensorsResult] = await Promise.all([
        settle(getJson<HealthResponse>("/health")),
        settle(getJson<AlertStats>("/alerts/stats")),
        settle(getJson<SensorOut[]>("/sensors")),
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
        const items = await getJson<AlertOut[]>("/alerts?limit=50");
        if (!cancelled) {
          setAlerts((current) => mergeAlerts(current, items));
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

  useEffect(() => {
    let stopped = false;
    let socket: WebSocket | null = null;
    let retryTimer: number | undefined;
    let attempt = 0;

    const refresh = async () => {
      try {
        const items = await getJson<AlertOut[]>("/alerts?limit=50");
        if (!stopped) setAlerts((current) => mergeAlerts(current, items));
      } catch {
        // Keep the last good feed; the next reconnect retries.
      }
    };

    const open = () => {
      socket = connect("/ws/alerts");
      socket.onopen = () => {
        attempt = 0;
        void refresh();
      };
      socket.onmessage = (event) => {
        try {
          const alert = JSON.parse(event.data as string) as AlertOut;
          setAlerts((current) => mergeAlerts(current, [alert]));
        } catch {
          return;
        }
      };
      socket.onclose = () => {
        if (stopped) return;
        attempt += 1;
        retryTimer = window.setTimeout(open, Math.min(15000, attempt * 2000));
      };
    };

    open();

    return () => {
      stopped = true;
      if (retryTimer !== undefined) window.clearTimeout(retryTimer);
      socket?.close();
    };
  }, []);

  useEffect(() => {
    let stopped = false;
    let socket: WebSocket | null = null;
    let retryTimer: number | undefined;
    let attempt = 0;
    let received = 0;
    let lastFrame: Date | null = null;

    const tick = window.setInterval(() => {
      setFrameCount(received);
      setLastFrameAt(lastFrame);
    }, 1000);

    const open = () => {
      socket = connect("/ws/frames");
      socket.onopen = () => {
        attempt = 0;
        setFramesConnected(true);
      };
      socket.onmessage = () => {
        received += 1;
        lastFrame = new Date();
      };
      socket.onclose = () => {
        if (stopped) return;
        setFramesConnected(false);
        attempt += 1;
        retryTimer = window.setTimeout(open, Math.min(15000, attempt * 2000));
      };
    };

    open();

    return () => {
      stopped = true;
      window.clearInterval(tick);
      if (retryTimer !== undefined) window.clearTimeout(retryTimer);
      socket?.close();
    };
  }, []);

  const advanceAlert = async (alert: AlertOut) => {
    const next: "acknowledged" | "resolved" =
      alert.status === "new" ? "acknowledged" : "resolved";
    setPendingAlertId(alert.alert_id);
    setActionError(null);
    try {
      const updated = await patchJson<AlertOut>(`/alerts/${alert.alert_id}`, {
        status: next,
      });
      setAlerts((current) =>
        (current ?? []).map((item) =>
          item.alert_id === updated.alert_id ? updated : item,
        ),
      );
    } catch (error) {
      setActionError(errorMessage(error));
    } finally {
      setPendingAlertId(null);
    }
  };

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
    <>
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
          Could not load /alerts: {alertsError}
        </div>
      )}

      {actionError && (
        <div className="error-banner" role="alert">
          Could not update alert: {actionError}
        </div>
      )}

      <div className="card">
        {alertsLoading && <div className="state-message">Loading alerts…</div>}

        {!alertsLoading && !alertsError && alerts?.length === 0 && (
          <div className="state-message">
            No alerts have been returned by the backend.
          </div>
        )}

        {alerts?.map((alert) => (
          <div className="alert-row" key={alert.alert_id}>
            <div className="alert-title">
              {alert.title}{" "}
              <span className={`sev-badge ${severityClass(alert.severity)}`}>
                SEV {alert.severity}
              </span>{" "}
              <span className={`status-badge status-${alert.status}`}>
                {alert.status}
              </span>
            </div>
            <div className="alert-meta">{formatLocal(alert.created_at)}</div>
            <div className="alert-meta">{alert.explanation}</div>
            <div className="alert-action">
              <strong>Suggested action:</strong>{" "}
              {alert.recommended_action}
            </div>
            {alert.status !== "resolved" && (
              <button
                className="alert-action-button"
                onClick={() => void advanceAlert(alert)}
                disabled={pendingAlertId === alert.alert_id}
              >
                {pendingAlertId === alert.alert_id
                  ? "Saving…"
                  : alert.status === "new"
                    ? "Acknowledge"
                    : "Mark resolved"}
              </button>
            )}
          </div>
        ))}
      </div>

      <div className="section-title">Sensors</div>
      <div className="card">
        {sensors === null && (
          <div className="state-message">Loading sensors…</div>
        )}

        {sensors?.length === 0 && (
          <div className="state-message">No sensors registered.</div>
        )}

        {sensors?.map((sensor) => (
          <div className="sensor-row" key={sensor.sensor_id}>
            <span
              className={`status-dot status-${sensor.status}`}
              aria-hidden="true"
            />
            <span className="sensor-name">
              {sensor.name ?? sensor.sensor_id}
            </span>
            <span className="sensor-meta">
              {sensor.location ?? "No location"} · {sensor.sensor_id}
            </span>
            <span className={`sensor-status status-${sensor.status}`}>
              {sensor.status}
            </span>
            <span className="sensor-meta">
              {sensor.last_seen_at
                ? `Last seen ${formatLocal(sensor.last_seen_at)}`
                : "Never seen"}
            </span>
          </div>
        ))}
      </div>

      <div className="section-title">Live Frame Activity</div>
      <div className="card frame-pulse">
        <span
          className={`pulse-dot ${framesConnected ? "is-live" : "is-down"}`}
          aria-hidden="true"
        />
        <div>
          <div className="value">{frameCount}</div>
          <div className="alert-meta">
            frames received · {framesConnected ? "stream connected" : "reconnecting"}
          </div>
          <div className="alert-meta">
            {lastFrameAt
              ? `Last frame: ${lastFrameAt.toLocaleTimeString()}`
              : "Waiting for the first frame…"}
          </div>
        </div>
      </div>
    </>
  );
}
