import {
  Activity,
  BarChart3,
  CheckCircle2,
  Globe2,
  LayoutDashboard,
  Radar,
  Search,
  Settings,
  Sparkles,
} from "lucide-react";
import { useEffect, useState } from "react";

import { defaultBrand, applyBrand, type BrandSettings } from "../config/brand";
import { PublishingReview } from "../features/publishing/PublishingReview";
import { AiSettingsPanel } from "../features/settings/AiSettingsPanel";
import {
  ProjectSwitcher,
  type ProjectSummary,
} from "../features/projects/ProjectSwitcher";
import { CreateProjectDialog } from "../features/projects/CreateProjectDialog";
import {
  DashboardModes,
  type DashboardView,
} from "../features/preferences/DashboardModes";
import {
  I18nProvider,
} from "../features/preferences/i18n";
import type { Locale } from "../features/preferences/i18n-core";
import { useI18n } from "../features/preferences/useI18n";
import { preferenceStorage } from "../features/preferences/storage";
import { CrawlPage } from "../routes/dashboard/CrawlPage";
import { Ga4Page } from "../routes/dashboard/Ga4Page";
import { OpportunitiesPage } from "../routes/dashboard/OpportunitiesPage";
import { PriorityPage } from "../routes/dashboard/PriorityPage";
import { SearchConsolePage } from "../routes/dashboard/SearchConsolePage";
import { ActionWorkspace } from "../routes/dashboard/views/ActionWorkspace";

const initialProjects: ProjectSummary[] = [
  {
    id: "shm",
    organizationId: "org-member",
    name: "SHM Transmissie",
    domain: "https://shmtransmissie.nl",
  },
  {
    id: "demo",
    organizationId: "org-member",
    name: "Demo project",
    domain: "https://demo.wpfixpilot.nl",
  },
];

export function App() {
  const [locale, setLocale] = useState<Locale>(
    (preferenceStorage.get("locale") as Locale | null) ?? "nl",
  );
  const [brand, setBrand] = useState<BrandSettings>(() => {
    const saved = preferenceStorage.get("brand-settings");
    return saved ? (JSON.parse(saved) as BrandSettings) : defaultBrand;
  });

  useEffect(() => applyBrand(brand), [brand]);

  return (
    <I18nProvider locale={locale}>
      <AppShell
        brand={brand}
        locale={locale}
        onBrandChange={(next) => {
          setBrand(next);
          preferenceStorage.set("brand-settings", JSON.stringify(next));
        }}
        onLocaleChange={(next) => {
          setLocale(next);
          preferenceStorage.set("locale", next);
        }}
      />
    </I18nProvider>
  );
}

function AppShell({
  brand,
  locale,
  onBrandChange,
  onLocaleChange,
}: {
  brand: BrandSettings;
  locale: Locale;
  onBrandChange: (brand: BrandSettings) => void;
  onLocaleChange: (locale: Locale) => void;
}) {
  const { t } = useI18n();
  const [route, setRoute] = useState(
    () => window.location.hash.slice(1) || "overview",
  );
  const [projects, setProjects] = useState(initialProjects);
  const [activeProjectId, setActiveProjectId] = useState(projects[0].id);
  const [showCreateProject, setShowCreateProject] = useState(false);

  useEffect(() => {
    const updateRoute = () =>
      setRoute(window.location.hash.slice(1) || "overview");
    window.addEventListener("hashchange", updateRoute);
    return () => window.removeEventListener("hashchange", updateRoute);
  }, []);

  const navigate = (next: string) => ({
    href: `#${next}`,
    className: `nav-item ${route === next ? "active" : ""}`,
  });

  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="Hoofdnavigatie">
        <a className="brand" href="#overview" aria-label={`${brand.name} home`}>
          <span>{brand.name.charAt(0).toUpperCase()}</span>
          <strong>{brand.name}</strong>
        </a>
        <nav>
          <a {...navigate("overview")}>
            <LayoutDashboard size={18} /> {t("overview")}
          </a>
          <a {...navigate("search-console")}>
            <Search size={18} /> Search Console
          </a>
          <a {...navigate("ga4")}>
            <BarChart3 size={18} /> GA4
          </a>
          <a {...navigate("crawl")}>
            <Radar size={18} /> Crawl
          </a>
          <a {...navigate("actions")}>
            <CheckCircle2 size={18} /> {t("actions")}
          </a>
          <a {...navigate("opportunities")}>
            <Sparkles size={18} /> {t("opportunities")}
          </a>
          <a {...navigate("priorities")}>
            <Activity size={18} /> {t("priorities")}
          </a>
        </nav>
        <a {...navigate("settings")} className={`nav-item settings-link ${route === "settings" ? "active" : ""}`}>
          <Settings size={18} /> {t("settings")}
        </a>
      </aside>

      <main className="workspace">
        <header className="topbar">
          <ProjectSwitcher
            projects={projects}
            activeProjectId={activeProjectId}
            onSelect={setActiveProjectId}
            onCreate={() => setShowCreateProject(true)}
          />
          <div className="topbar-actions">
            <label className="search-field">
              <Search size={16} />
              <span className="sr-only">Zoeken</span>
              <input placeholder="Zoek pagina of issue" />
            </label>
            <button className="sync-button" type="button">
              <Activity size={16} /> Synchroniseren
            </button>
          </div>
        </header>
        <RouteContent
          route={route}
          activeProject={
            projects.find((project) => project.id === activeProjectId) ??
            projects[0]
          }
          brand={brand}
          locale={locale}
          onBrandChange={onBrandChange}
          onLocaleChange={onLocaleChange}
        />
      </main>
      {showCreateProject && (
        <CreateProjectDialog
          onClose={() => setShowCreateProject(false)}
          onSubmit={(draft) => {
            const project = {
              ...draft,
              id: crypto.randomUUID(),
              organizationId: "org-member",
            };
            setProjects((current) => [...current, project]);
            setActiveProjectId(project.id);
            setShowCreateProject(false);
          }}
        />
      )}
    </div>
  );
}

function RouteContent({
  route,
  activeProject,
  brand,
  locale,
  onBrandChange,
  onLocaleChange,
}: {
  route: string;
  activeProject: ProjectSummary;
  brand: BrandSettings;
  locale: Locale;
  onBrandChange: (brand: BrandSettings) => void;
  onLocaleChange: (locale: Locale) => void;
}) {
  if (route === "search-console") return <SearchConsolePage />;
  if (route === "ga4") return <Ga4Page />;
  if (route === "crawl") return <CrawlPage projectId={activeProject.id} />;
  if (route === "actions")
    return (
      <div className="content">
        <ActionWorkspace projectId={activeProject.id} />
      </div>
    );
  if (route === "opportunities") return <OpportunitiesPage />;
  if (route === "priorities") return <PriorityPage />;
  if (route === "publishing")
    return <PublishingReview projectId={activeProject.id} />;
  if (route === "settings")
    return (
      <SettingsPanel
        activeProject={activeProject}
        brand={brand}
        locale={locale}
        onBrandChange={onBrandChange}
        onLocaleChange={onLocaleChange}
      />
    );
  return (
    <div className="content dashboard-mode-container">
      <DashboardModes
        brandName={brand.name}
        projectId={activeProject.id}
        savedView={
          (preferenceStorage.get("dashboard-view") as DashboardView | null) ??
          "hybrid"
        }
      />
    </div>
  );
}

function SettingsPanel({
  activeProject,
  brand,
  locale,
  onBrandChange,
  onLocaleChange,
}: {
  activeProject: ProjectSummary;
  brand: BrandSettings;
  locale: Locale;
  onBrandChange: (brand: BrandSettings) => void;
  onLocaleChange: (locale: Locale) => void;
}) {
  return (
    <section className="data-page settings-page">
      <p className="eyebrow">Personalisatie</p>
      <h1>Instellingen</h1>
      <p className="subtitle">
        Wijzig taal, productnaam en kleuren zonder de applicatie om te bouwen.
      </p>
      <div className="settings-form">
        <label>
          Productnaam
          <input
            value={brand.name}
            onChange={(event) =>
              onBrandChange({ ...brand, name: event.target.value })
            }
          />
        </label>
        <label>
          Hoofdkleur
          <input
            type="color"
            value={brand.primaryColor}
            onChange={(event) =>
              onBrandChange({ ...brand, primaryColor: event.target.value })
            }
          />
        </label>
        <label>
          Accentkleur
          <input
            type="color"
            value={brand.accentColor}
            onChange={(event) =>
              onBrandChange({ ...brand, accentColor: event.target.value })
            }
          />
        </label>
        <fieldset>
          <legend>
            <Globe2 size={15} /> Taal
          </legend>
          <button
            className={locale === "nl" ? "selected" : ""}
            onClick={() => onLocaleChange("nl")}
            type="button"
          >
            Nederlands
          </button>
          <button
            className={locale === "en" ? "selected" : ""}
            onClick={() => onLocaleChange("en")}
            type="button"
          >
            English
          </button>
        </fieldset>
      </div>
      <AiSettingsPanel
        organizationId={activeProject.organizationId}
        projectId={activeProject.id}
      />
    </section>
  );
}
