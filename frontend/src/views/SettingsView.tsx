import { useState, type FormEvent } from "react";
import { getAdminKey, setAdminKey } from "../api";
import { t, type Lang } from "../i18n";

export default function SettingsView({ lang }: { lang: Lang }) {
  const [key, setKey] = useState(() => getAdminKey() ?? "");
  const [saved, setSaved] = useState(false);

  const save = (event: FormEvent) => {
    event.preventDefault();
    setAdminKey(key.trim());
    setSaved(true);
  };

  const clear = () => {
    setAdminKey("");
    setKey("");
    setSaved(true);
  };

  return (
    <form className="card" onSubmit={save}>
      <h3>{t(lang, "settings.adminKey")}</h3>
      <label className="field">
        {t(lang, "settings.adminKey")}
        <input
          type="password"
          value={key}
          autoComplete="off"
          onChange={(event) => {
            setKey(event.target.value);
            setSaved(false);
          }}
        />
      </label>
      <div className="button-row">
        <button type="submit" className="primary-button">
          {t(lang, "settings.saveKey")}
        </button>
        <button type="button" className="retry-button" onClick={clear}>
          {t(lang, "settings.clearKey")}
        </button>
      </div>
      <p className="inline-note">{t(lang, "settings.keyNote")}</p>
      {saved && <p className="inline-note">Saved for this tab.</p>}
    </form>
  );
}
