import { useEffect, useState } from "react";
import {
  API_BASE,
  delJson,
  errorMessage,
  getJson,
  postJson,
  type SiteOut,
  type TrustOut,
} from "../api";
import { siteOptionLabel, t, type Lang } from "../i18n";

export default function TrustView({ lang }: { lang: Lang }) {
  const [sites, setSites] = useState<SiteOut[] | null>(null);
  const [siteId, setSiteId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

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

  const selected =
    sites?.find((site) => site.site_id === siteId) ?? sites?.[0] ?? null;

  const replaceSite = (updated: SiteOut) => {
    setSites((current) =>
      (current ?? []).map((site) =>
        site.site_id === updated.site_id ? updated : site,
      ),
    );
  };

  const enroll = async () => {
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      const result = await postJson<TrustOut>(
        `/sites/${selected.site_id}/trust`,
        {},
      );
      replaceSite({ ...selected, trust_token: result.trust_token });
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  };

  const revoke = async () => {
    if (!selected) return;
    const confirmed = window.confirm(
      "Revoke the public link? Anyone holding the old QR will get a 404.",
    );
    if (!confirmed) return;

    setBusy(true);
    setError(null);
    try {
      await delJson<void>(`/sites/${selected.site_id}/trust`);
      replaceSite({ ...selected, trust_token: null });
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  };

  const token = selected?.trust_token ?? null;
  const publicUrl = token ? `${API_BASE}/trust/${token}` : null;

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

      {selected && (
        <>
          <label className="field">
            {t(lang, "common.selectSite")}
            <select
              value={selected.site_id}
              onChange={(event) => setSiteId(event.target.value)}
            >
              {sites?.map((site) => (
                <option key={site.site_id} value={site.site_id}>
                  {siteOptionLabel(site)}
                </option>
              ))}
            </select>
          </label>

          <div className="card">
            {token && publicUrl ? (
              <>
                <h3>{t(lang, "trust.link")}</h3>
                <p>
                  <a href={publicUrl} target="_blank" rel="noreferrer">
                    {publicUrl}
                  </a>
                </p>
                <img
                  className="qr"
                  src={`${publicUrl}/qr.png`}
                  alt="QR code for the public trust page"
                />
              </>
            ) : (
              <div className="state-message">
                This site has no public trust link yet.
              </div>
            )}

            <div className="button-row">
              <button
                type="button"
                className="primary-button"
                onClick={() => void enroll()}
                disabled={busy}
              >
                {token ? t(lang, "trust.rotate") : t(lang, "trust.enroll")}
              </button>
              {token && (
                <button
                  type="button"
                  className="danger-button"
                  onClick={() => void revoke()}
                  disabled={busy}
                >
                  {t(lang, "trust.revoke")}
                </button>
              )}
            </div>

            <p className="inline-note">{t(lang, "trust.languageNote")}</p>
          </div>
        </>
      )}
    </>
  );
}
