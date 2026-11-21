import { useEffect, useState, type FormEvent } from "react";
import {
  delJson,
  errorMessage,
  getJson,
  patchJson,
  postJson,
  type SensorOut,
  type SiteOut,
} from "../api";
import { siteLabel, t, type Lang } from "../i18n";

interface Draft {
  site_id: string;
  business_name: string;
  business_type: string;
  wifi_ssids: string;
  known_access_points: string;
  router_model: string;
  primary_language: string;
  notes: string;
}

const EMPTY_DRAFT: Draft = {
  site_id: "",
  business_name: "",
  business_type: "",
  wifi_ssids: "",
  known_access_points: "",
  router_model: "",
  primary_language: "en",
  notes: "",
};

function splitList(value: string): string[] {
  return value
    .split(/[\s,]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function draftFrom(site: SiteOut): Draft {
  return {
    site_id: site.site_id,
    business_name: site.business_name ?? "",
    business_type: site.business_type ?? "",
    wifi_ssids: site.wifi_ssids.join(", "),
    known_access_points: site.known_access_points.join(", "),
    router_model: site.router_model ?? "",
    primary_language: site.primary_language,
    notes: site.notes ?? "",
  };
}

// PATCH semantics: an empty optional field is sent as null, which clears it.
// Null on wifi_ssids / known_access_points would be ignored by the backend,
// so those two always travel as arrays.
function siteBody(draft: Draft, siteId: string | null) {
  const body: Record<string, unknown> = {
    business_name: draft.business_name.trim() || null,
    business_type: draft.business_type.trim() || null,
    router_model: draft.router_model.trim() || null,
    notes: draft.notes.trim() || null,
    wifi_ssids: splitList(draft.wifi_ssids),
    known_access_points: splitList(draft.known_access_points),
    primary_language: draft.primary_language,
  };
  if (siteId) body.site_id = siteId;
  return body;
}

function TextField({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}) {
  return (
    <label className="field">
      {label}
      <input
        value={value}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}

function SiteFields({
  draft,
  onChange,
}: {
  draft: Draft;
  onChange: (draft: Draft) => void;
}) {
  const set = (key: keyof Draft) => (value: string) =>
    onChange({ ...draft, [key]: value } as Draft);

  return (
    <div className="form-grid">
      <TextField label="Business name" value={draft.business_name} onChange={set("business_name")} />
      <TextField label="Business type" value={draft.business_type} onChange={set("business_type")} />
      <TextField
        label="WiFi network names (comma separated)"
        value={draft.wifi_ssids}
        onChange={set("wifi_ssids")}
      />
      <TextField
        label="Known access points (MAC, comma separated)"
        value={draft.known_access_points}
        onChange={set("known_access_points")}
        placeholder="AA:BB:CC:DD:EE:FF"
      />
      <TextField label="Router model" value={draft.router_model} onChange={set("router_model")} />
      <label className="field">
        Primary language
        <select
          value={draft.primary_language}
          onChange={(event) => set("primary_language")(event.target.value)}
        >
          <option value="en">English</option>
          <option value="ar">Arabic</option>
        </select>
      </label>
      <label className="field">
        Notes
        <textarea
          value={draft.notes}
          onChange={(event) => set("notes")(event.target.value)}
        />
      </label>
    </div>
  );
}

function SiteEditor({
  site,
  lang,
  onSaved,
  onError,
}: {
  site: SiteOut;
  lang: Lang;
  onSaved: (site: SiteOut) => void;
  onError: (message: string | null) => void;
}) {
  const [draft, setDraft] = useState<Draft>(() => draftFrom(site));
  const [busy, setBusy] = useState(false);

  const save = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    onError(null);
    try {
      const updated = await patchJson<SiteOut>(
        `/sites/${site.site_id}`,
        siteBody(draft, null),
      );
      // Show the normalized MACs the backend now holds, not what was typed.
      setDraft(draftFrom(updated));
      onSaved(updated);
    } catch (error) {
      onError(errorMessage(error));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="card" onSubmit={(event) => void save(event)}>
      <div className="section-heading">
        <div className="section-title">{t(lang, "sites.edit")}</div>
      </div>
      <SiteFields draft={draft} onChange={setDraft} />
      <p className="inline-note">{t(lang, "sites.normalized")}</p>
      <button type="submit" className="primary-button" disabled={busy}>
        {t(lang, "common.save")}
      </button>
    </form>
  );
}

export default function SitesView({ lang }: { lang: Lang }) {
  const [sites, setSites] = useState<SiteOut[] | null>(null);
  const [sensors, setSensors] = useState<SensorOut[] | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [createDraft, setCreateDraft] = useState<Draft>(EMPTY_DRAFT);
  const [creating, setCreating] = useState(false);
  const [pendingSensorId, setPendingSensorId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const [siteList, sensorList] = await Promise.all([
          getJson<SiteOut[]>("/sites"),
          getJson<SensorOut[]>("/sensors"),
        ]);
        if (!cancelled) {
          setSites(siteList);
          setSensors(sensorList);
          setError(null);
        }
      } catch (caught) {
        if (!cancelled) setError(errorMessage(caught));
      }
    };

    void load();

    return () => {
      cancelled = true;
    };
  }, []);

  const selected =
    sites?.find((site) => site.site_id === selectedId) ?? sites?.[0] ?? null;

  const create = async (event: FormEvent) => {
    event.preventDefault();
    setCreating(true);
    setError(null);
    try {
      const created = await postJson<SiteOut>(
        "/sites",
        siteBody(createDraft, createDraft.site_id.trim()),
      );
      setSites((current) => [...(current ?? []), created]);
      setSelectedId(created.site_id);
      setCreateDraft(EMPTY_DRAFT);
      setShowCreate(false);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setCreating(false);
    }
  };

  const replaceSite = (updated: SiteOut) => {
    setSites((current) =>
      (current ?? []).map((site) =>
        site.site_id === updated.site_id ? updated : site,
      ),
    );
  };

  const toggleSensor = async (sensor: SensorOut) => {
    if (!selected) return;
    setPendingSensorId(sensor.sensor_id);
    setError(null);
    const path = `/sites/${selected.site_id}/sensors/${sensor.sensor_id}`;
    try {
      const updated =
        sensor.site_id === selected.site_id
          ? await delJson<SensorOut>(path)
          : await patchJson<SensorOut>(path, {});
      setSensors((current) =>
        (current ?? []).map((item) =>
          item.sensor_id === updated.sensor_id ? updated : item,
        ),
      );
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setPendingSensorId(null);
    }
  };

  return (
    <>
      {error && (
        <div className="error-banner" role="alert">
          {error}
        </div>
      )}

      <div className="section-heading">
        <div className="section-title">{t(lang, "view.sites")}</div>
        <button
          type="button"
          className="retry-button"
          onClick={() => setShowCreate((open) => !open)}
        >
          {t(lang, "sites.new")}
        </button>
      </div>

      {showCreate && (
        <form className="card" onSubmit={(event) => void create(event)}>
          <div className="form-grid">
            <label className="field">
              Site ID
              <input
                value={createDraft.site_id}
                onChange={(event) =>
                  setCreateDraft({ ...createDraft, site_id: event.target.value })
                }
                required
              />
            </label>
          </div>
          <SiteFields
            draft={createDraft}
            onChange={(draft) =>
              setCreateDraft({ ...draft, site_id: createDraft.site_id })
            }
          />
          <button type="submit" className="primary-button" disabled={creating}>
            {t(lang, "common.create")}
          </button>
        </form>
      )}

      {sites === null && <div className="state-message">{t(lang, "common.loading")}</div>}

      {sites?.length === 0 && (
        <div className="state-message">{t(lang, "common.noSites")}</div>
      )}

      {sites && sites.length > 0 && (
        <div className="site-tabs">
          {sites.map((site) => {
            const label = siteLabel(site);
            return (
              <button
                key={site.site_id}
                type="button"
                className={`site-tab${
                  selected?.site_id === site.site_id ? " is-active" : ""
                }`}
                onClick={() => setSelectedId(site.site_id)}
              >
                {label}
                {label !== site.site_id && (
                  <span className="sensor-meta"> · {site.site_id}</span>
                )}
              </button>
            );
          })}
        </div>
      )}

      {selected && (
        <SiteEditor
          key={selected.site_id}
          site={selected}
          lang={lang}
          onSaved={replaceSite}
          onError={setError}
        />
      )}

      {selected && (
        <>
          <div className="section-title">{t(lang, "sites.sensors")}</div>
          <div className="card">
            {sensors === null && (
              <div className="state-message">{t(lang, "common.loading")}</div>
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
                <span className="sensor-name">{sensor.sensor_id}</span>
                <span className="sensor-meta">
                  {sensor.site_id
                    ? `Site: ${sensor.site_id}`
                    : "Unassigned"}
                </span>
                <span className={`sensor-status status-${sensor.status}`}>
                  {sensor.status}
                </span>
                <button
                  type="button"
                  className="alert-action-button"
                  disabled={pendingSensorId === sensor.sensor_id}
                  onClick={() => void toggleSensor(sensor)}
                >
                  {sensor.site_id === selected.site_id
                    ? t(lang, "sites.unassign")
                    : t(lang, "sites.assign")}
                </button>
              </div>
            ))}
          </div>
        </>
      )}
    </>
  );
}
