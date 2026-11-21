import { useEffect, useState } from "react";
import { t, type Lang } from "./i18n";
import DashboardView from "./views/DashboardView";
import SitesView from "./views/SitesView";
import ChecklistView from "./views/ChecklistView";
import ScoreView from "./views/ScoreView";
import TrustView from "./views/TrustView";
import SettingsView from "./views/SettingsView";

// No router: a rejected dependency. View state is a single union member.
const VIEWS = [
  { id: "dashboard", labelKey: "nav.dashboard" },
  { id: "sites", labelKey: "nav.sites" },
  { id: "checklist", labelKey: "nav.checklist" },
  { id: "score", labelKey: "nav.score" },
  { id: "trust", labelKey: "nav.trust" },
  { id: "settings", labelKey: "nav.settings" },
] as const;

type ViewId = (typeof VIEWS)[number]["id"];

export default function App() {
  const [view, setView] = useState<ViewId>("dashboard");
  const [lang, setLang] = useState<Lang>("en");

  useEffect(() => {
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
  }, [lang]);

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">PRODOS</div>
        {VIEWS.map((item) => (
          <button
            key={item.id}
            type="button"
            className={`nav-item${view === item.id ? " active" : ""}`}
            aria-current={view === item.id ? "page" : undefined}
            onClick={() => setView(item.id)}
          >
            {t(lang, item.labelKey)}
          </button>
        ))}
      </aside>

      <header className="header">
        <h1>{t(lang, `view.${view}`)}</h1>
        <div className="header-tools">
          <button
            type="button"
            className="ghost-button"
            onClick={() => setLang(lang === "en" ? "ar" : "en")}
            title="Switch language"
          >
            {lang === "en" ? "AR" : "EN"}
          </button>
        </div>
      </header>

      <main className="main">
        {view === "dashboard" && <DashboardView />}
        {view === "sites" && <SitesView lang={lang} />}
        {view === "checklist" && <ChecklistView lang={lang} />}
        {view === "score" && <ScoreView lang={lang} />}
        {view === "trust" && <TrustView lang={lang} />}
        {view === "settings" && <SettingsView lang={lang} />}
      </main>
    </div>
  );
}
