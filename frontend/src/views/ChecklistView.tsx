import { useEffect, useState } from "react";
import {
  ApiError,
  errorMessage,
  formatLocal,
  getJson,
  putJson,
  type ChecklistOut,
  type SiteOut,
} from "../api";
import {
  CHECKLIST_KEYS,
  CHECKLIST_QUESTIONS,
  questionText,
  siteOptionLabel,
  t,
  type Lang,
} from "../i18n";

interface Rejection {
  unknownKeys: string[];
  validKeys: string[];
}

function rejectionOf(caught: unknown): Rejection | null {
  if (!(caught instanceof ApiError) || caught.status !== 422) return null;
  const detail = (caught.body as { detail?: Record<string, unknown> } | null)
    ?.detail;
  if (!detail) return null;

  const strings = (value: unknown) =>
    Array.isArray(value)
      ? value.filter((item): item is string => typeof item === "string")
      : [];

  return {
    unknownKeys: strings(detail.unknown_keys),
    validKeys: strings(detail.valid_keys),
  };
}

function ChecklistForm({ siteId, lang }: { siteId: string; lang: Lang }) {
  const [answers, setAnswers] = useState<Record<string, boolean | null>>({});
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rejection, setRejection] = useState<Rejection | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const data = await getJson<ChecklistOut>(
          `/sites/${siteId}/checklist`,
        );
        if (!cancelled) {
          setAnswers(data.answers);
          setUpdatedAt(data.updated_at);
          setError(null);
        }
      } catch (caught) {
        if (!cancelled) setError(errorMessage(caught));
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    void load();

    return () => {
      cancelled = true;
    };
  }, [siteId]);

  const save = async () => {
    setSaving(true);
    setError(null);
    setRejection(null);
    const payload: Record<string, boolean> = {};
    for (const key of CHECKLIST_KEYS) payload[key] = answers[key] === true;

    try {
      const data = await putJson<ChecklistOut>(`/sites/${siteId}/checklist`, {
        answers: payload,
      });
      setAnswers(data.answers);
      setUpdatedAt(data.updated_at);
    } catch (caught) {
      setRejection(rejectionOf(caught));
      setError(errorMessage(caught));
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <div className="state-message">{t(lang, "common.loading")}</div>;

  const answered = CHECKLIST_KEYS.some((key) => answers[key] !== undefined);

  return (
    <>
      {error && (
        <div className="error-banner" role="alert">
          {error}
        </div>
      )}

      {rejection && (
        <div className="error-banner" role="alert">
          <p>These keys are not part of the checklist:</p>
          <ul>
            {rejection.unknownKeys.map((key) => (
              <li key={key}>{key}</li>
            ))}
          </ul>
          <p>
            Accepted keys: {rejection.validKeys.join(", ") || "none reported"}
          </p>
        </div>
      )}

      {!answered && !error && (
        <div className="state-message">{t(lang, "checklist.empty")}</div>
      )}

      <div className="card">
        {CHECKLIST_QUESTIONS.map((question) => (
          <label key={question.key} className="checkbox-row">
            <input
              type="checkbox"
              checked={answers[question.key] === true}
              onChange={(event) =>
                setAnswers((current) => ({
                  ...current,
                  [question.key]: event.target.checked,
                }))
              }
            />
            <span>
              {questionText(question, lang)}
              <span className="sensor-meta"> · {question.key}</span>
            </span>
          </label>
        ))}
      </div>

      <div className="section-heading">
        <button
          type="button"
          className="primary-button"
          onClick={() => void save()}
          disabled={saving}
        >
          {t(lang, "checklist.save")}
        </button>
        {updatedAt && (
          <span className="inline-note">
            {t(lang, "common.updated")} {formatLocal(updatedAt)}
          </span>
        )}
      </div>
    </>
  );
}

export default function ChecklistView({ lang }: { lang: Lang }) {
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
        <ChecklistForm key={activeSiteId} siteId={activeSiteId} lang={lang} />
      )}
    </>
  );
}
