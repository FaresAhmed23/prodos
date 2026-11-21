import { useEffect, useState } from "react";
import {
  ApiError,
  errorMessage,
  formatLocal,
  getJson,
  type ScoreOut,
  type SiteOut,
} from "../api";
import {
  SCORE_COMPONENTS,
  SCORE_FLAGS,
  componentLabel,
  siteOptionLabel,
  t,
  type Lang,
} from "../i18n";

function flagsOf(score: ScoreOut): string[] {
  const value = score.details.flags;
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

function bandClass(band: string): string {
  if (band === "good") return "band-good";
  if (band === "fair") return "band-fair";
  return "band-bad";
}

function Sparkline({ scores }: { scores: number[] }) {
  if (scores.length < 2) return null;
  const points = scores
    .map((value, index) => {
      const x = (index / (scores.length - 1)) * 100;
      const y = 100 - Math.min(100, Math.max(0, value));
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  return (
    <svg
      className="sparkline"
      viewBox="0 0 100 100"
      preserveAspectRatio="none"
      role="img"
      aria-label="Score history"
    >
      <polyline points={points} />
    </svg>
  );
}

function ScorePanel({ siteId, lang }: { siteId: string; lang: Lang }) {
  const [score, setScore] = useState<ScoreOut | null>(null);
  const [history, setHistory] = useState<ScoreOut[]>([]);
  const [notReady, setNotReady] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const latest = await getJson<ScoreOut>(`/sites/${siteId}/score`);
        if (!cancelled) setScore(latest);
      } catch (caught) {
        if (!cancelled) {
          if (caught instanceof ApiError && caught.status === 404) {
            setNotReady(true);
          } else {
            setError(errorMessage(caught));
          }
        }
      }

      try {
        const rows = await getJson<ScoreOut[]>(
          `/sites/${siteId}/score/history?limit=30`,
        );
        if (!cancelled) setHistory(rows);
      } catch (caught) {
        if (!cancelled) setError(errorMessage(caught));
      }
    };

    void load();

    return () => {
      cancelled = true;
    };
  }, [siteId]);

  if (error) {
    return (
      <div className="error-banner" role="alert">
        {error}
      </div>
    );
  }

  if (notReady) {
    return <div className="state-message">{t(lang, "score.noSnapshot")}</div>;
  }

  if (score === null) {
    return <div className="state-message">{t(lang, "common.loading")}</div>;
  }

  const flags = flagsOf(score);

  return (
    <>
      <div className="stat-grid">
        <div className="card">
          <h3>Score</h3>
          <div className="value">{score.score}</div>
          <div className={`band-badge ${bandClass(score.band)}`}>{score.band}</div>
        </div>
        <div className="card">
          <h3>Computed</h3>
          <div className="value small">{formatLocal(score.computed_at)}</div>
          <div className="alert-meta">Window: {score.window_days} days</div>
        </div>
      </div>

      <div className="section-title">{t(lang, "score.components")}</div>
      <div className="card">
        {SCORE_COMPONENTS.map((component) => {
          const value = score.components[component.key] ?? 0;
          const pct = Math.max(
            0,
            Math.min(100, (value / component.weight) * 100),
          );
          return (
            <div className="meter-row" key={component.key}>
              <div className="meter-head">
                <span>{componentLabel(component, lang)}</span>
                <span className="sensor-meta">
                  {value} / {component.weight}
                </span>
              </div>
              <div className="meter">
                <div style={{ width: `${pct}%` }} />
              </div>
            </div>
          );
        })}
      </div>

      {flags.length > 0 && (
        <>
          <div className="section-title">{t(lang, "score.flags")}</div>
          <div className="card">
            {flags.map((flag) => (
              <div className="alert-meta" key={flag}>
                • {SCORE_FLAGS[flag] ?? flag}
              </div>
            ))}
          </div>
        </>
      )}

      <div className="section-title">{t(lang, "score.history")}</div>
      <div className="card">
        {history.length === 0 && (
          <div className="state-message">No snapshots recorded yet.</div>
        )}
        <Sparkline scores={history.map((row) => row.score)} />
        {[...history].reverse().map((row) => (
          <div className="history-row" key={`${row.site_id}-${row.computed_at}`}>
            <span>{formatLocal(row.computed_at)}</span>
            <span className={`band-badge ${bandClass(row.band)}`}>{row.band}</span>
            <span>{row.score}</span>
          </div>
        ))}
      </div>
    </>
  );
}

export default function ScoreView({ lang }: { lang: Lang }) {
  const [sites, setSites] = useState<SiteOut[] | null>(null);
  const [siteId, setSiteId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const siteList = await getJson<SiteOut[]>("/sites");
        if (!cancelled) setSites(siteList);
      } catch (caught) {
        if (!cancelled) setError(errorMessage(caught));
      }
    };

    void load();

    return () => {
      cancelled = true;
    };
  }, []);

  const activeSiteId = siteId ?? sites?.[0]?.site_id ?? "";

  return (
    <>
      {error && (
        <div className="error-banner" role="alert">
          {error}
        </div>
      )}

      {sites === null && (
        <div className="state-message">{t(lang, "common.loading")}</div>
      )}

      {sites?.length === 0 && (
        <div className="state-message">{t(lang, "common.noSites")}</div>
      )}

      {sites && sites.length > 0 && (
        <label className="field">
          {t(lang, "common.selectSite")}
          <select
            value={activeSiteId}
            onChange={(event) => setSiteId(event.target.value)}
          >
            {sites.map((site) => (
              <option key={site.site_id} value={site.site_id}>
                {siteOptionLabel(site)}
              </option>
            ))}
          </select>
        </label>
      )}

      {activeSiteId && (
        <ScorePanel key={activeSiteId} siteId={activeSiteId} lang={lang} />
      )}
    </>
  );
}
