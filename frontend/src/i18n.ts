// One constants file: checklist wording, score component labels, UI strings.
// Checklist keys and English wording mirror backend/app/scoring/config.py
// verbatim. Never retype a key in a view.

export type Lang = "en" | "ar";

export interface ChecklistQuestion {
  key: string;
  en: string;
  // Arabic wording is Mohamed Ahmed's and lands later.
  ar?: string;
}

export const CHECKLIST_QUESTIONS: ChecklistQuestion[] = [
  {
    key: "router_admin_password_changed",
    en: "Router admin password changed from the factory default",
  },
  {
    key: "wpa2_or_wpa3",
    en: "Network encryption is WPA2 or WPA3 (not WEP, not open)",
  },
  {
    key: "guest_network_separate",
    en: "Customers use a separate guest network, apart from business devices",
  },
  {
    key: "firmware_updated_12m",
    en: "Router firmware updated in the last 12 months",
  },
  {
    key: "password_rotated_6m",
    en: "WiFi password changed in the last 6 months",
  },
  {
    key: "router_physically_secured",
    en: "Router sits in a protected spot, not publicly reachable",
  },
  {
    key: "no_unmanaged_extenders",
    en: "All extenders, repeaters, or extra routers were set up by staff or a trusted technician",
  },
  {
    key: "staff_share_password_in_person_only",
    en: "Staff share the WiFi password in person only (never posted or sent in chat)",
  },
];

export const CHECKLIST_KEYS = CHECKLIST_QUESTIONS.map((question) => question.key);

// Keys and weights mirror WEIGHTS in backend/app/scoring/config.py.
export const SCORE_COMPONENTS = [
  { key: "monitoring_coverage", en: "Monitoring coverage", weight: 30 },
  { key: "alert_response", en: "Alert response", weight: 30 },
  { key: "network_hygiene", en: "Network hygiene", weight: 15 },
  { key: "practices_checklist", en: "Practices checklist", weight: 15 },
  { key: "threat_exposure", en: "Threat exposure", weight: 10 },
];

export const SCORE_FLAGS: Record<string, string> = {
  no_sensors_assigned: "No sensors are assigned to this site",
  ssids_not_configured: "The site's WiFi network names are not configured",
};

const EN: Record<string, string> = {
  "nav.dashboard": "Dashboard",
  "nav.sites": "Sites",
  "nav.checklist": "Checklist",
  "nav.score": "Score",
  "nav.trust": "Trust page",
  "nav.settings": "Settings",
  "view.dashboard": "Security Dashboard",
  "view.sites": "Sites",
  "view.checklist": "WiFi safety checklist",
  "view.score": "ShieldScore",
  "view.trust": "Public trust page",
  "view.settings": "Settings",
  "common.loading": "Loading…",
  "common.retry": "Retry",
  "common.save": "Save",
  "common.create": "Create",
  "common.cancel": "Cancel",
  "common.remove": "Remove",
  "common.selectSite": "Select a site",
  "common.noSites": "No sites yet. Create one in Sites first.",
  "common.updated": "Updated",
  "sites.new": "New site",
  "sites.edit": "Edit site",
  "sites.sensors": "Sensors",
  "sites.assign": "Assign",
  "sites.unassign": "Unassign",
  "sites.normalized": "MAC addresses are stored upper-case and colon-separated.",
  "checklist.save": "Save checklist",
  "checklist.empty": "Nothing saved yet. Every unanswered question counts as no.",
  "score.noSnapshot": "No snapshot yet. The daily job writes one per site per day.",
  "score.history": "History",
  "score.components": "Components",
  "score.flags": "Flags",
  "trust.enroll": "Create trust link",
  "trust.rotate": "Rotate link",
  "trust.revoke": "Revoke",
  "trust.link": "Public link",
  "trust.languageNote": "The public page follows the site's primary language; it is rendered by the backend.",
  "settings.adminKey": "Admin key",
  "settings.saveKey": "Save key",
  "settings.clearKey": "Clear key",
  "settings.keyNote": "Stored in this tab's sessionStorage and sent as X-Admin-Key. It dies when the tab closes. Only enforced when the backend sets ADMIN_API_KEY.",
};

// Arabic wording is Mohamed Ahmed's, pending. Missing keys fall back to
// English, so the scaffold renders before a single string is translated.
const STRINGS: Record<Lang, Record<string, string>> = {
  en: EN,
  ar: {},
};

export function t(lang: Lang, key: string): string {
  return STRINGS[lang][key] ?? STRINGS.en[key] ?? key;
}

// A site with no business name is identified by its id, never by an empty
// string or the literal that a JSON null turns into in a careless template.
export function siteLabel(site: {
  site_id: string;
  business_name: string | null;
}): string {
  const name = site.business_name?.trim();
  return name ? name : site.site_id;
}

export function siteOptionLabel(site: {
  site_id: string;
  business_name: string | null;
}): string {
  const label = siteLabel(site);
  return label === site.site_id ? label : `${label} · ${site.site_id}`;
}

export function questionText(question: ChecklistQuestion, lang: Lang): string {
  return question[lang] ?? question.en;
}

export function componentLabel(
  component: { en: string; ar?: string },
  lang: Lang,
): string {
  return component[lang] ?? component.en;
}
