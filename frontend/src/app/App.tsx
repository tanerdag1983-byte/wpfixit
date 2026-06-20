import {
  Activity,
  BarChart3,
  CheckCircle2,
  Globe2,
  LayoutDashboard,
  LogOut,
  Radar,
  Search,
  Settings,
  Sparkles,
} from "lucide-react";
import { useEffect, useState } from "react";

import { defaultBrand, applyBrand, type BrandSettings } from "../config/brand";
import { PublishingReview } from "../features/publishing/PublishingReview";
import { GoogleOAuthCallback } from "../features/google/GoogleOAuthCallback";
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
import { apiRequest } from "../lib/api";
import { supabase } from "../lib/supabase";

type ProjectRead = {
  id: string;
  organization_id: string;
  name: string;
  domain: string;
};

type ProjectList = {
  items: ProjectRead[];
};

function toProjectSummary(project: ProjectRead): ProjectSummary {
  return {
    id: project.id,
    organizationId: project.organization_id,
    name: project.name,
    domain: project.domain,
  };
}

export function App() {
  const [locale, setLocale] = useState<Locale>(
    (preferenceStorage.get("locale") as Locale | null) ?? "nl",
  );
  const [brand, setBrand] = useState<BrandSettings>(() => {
    const saved = preferenceStorage.get("brand-settings");
    return saved ? (JSON.parse(saved) as BrandSettings) : defaultBrand;
  });

  useEffect(() => applyBrand(brand), [brand]);

  if (window.location.pathname === "/auth/google/callback") {
    return <GoogleOAuthCallback />;
  }

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
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [activeProjectId, setActiveProjectId] = useState(
    () => preferenceStorage.get("active-project-id") ?? "",
  );
  const [showCreateProject, setShowCreateProject] = useState(false);
  const [projectError, setProjectError] = useState<string | null>(null);
  const [projectsLoading, setProjectsLoading] = useState(true);
  const [creatingProject, setCreatingProject] = useState(false);

  useEffect(() => {
    const updateRoute = () =>
      setRoute(window.location.hash.slice(1) || "overview");
    window.addEventListener("hashchange", updateRoute);
    return () => window.removeEventListener("hashchange", updateRoute);
  }, []);

  useEffect(() => {
    let mounted = true;
    apiRequest<ProjectList>("/projects")
      .then((response) => {
        if (!mounted) return;
        const nextProjects = response.items.map(toProjectSummary);
        setProjects(nextProjects);
        setActiveProjectId((current) => {
          const nextProjectId = nextProjects.some((project) => project.id === current)
            ? current
            : nextProjects[0]?.id ?? "";
          if (nextProjectId) {
            preferenceStorage.set("active-project-id", nextProjectId);
          }
          return nextProjectId;
        });
        setProjectError(null);
      })
      .catch((error: Error) => {
        if (!mounted) return;
        setProjectError(error.message);
      })
      .finally(() => {
        if (mounted) setProjectsLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, []);

  const navigate = (next: string) => ({
    href: `#${next}`,
    className: `nav-item ${route === next ? "active" : ""}`,
  });
  const activeProject =
    projects.find((project) => project.id === activeProjectId) ?? projects[0];

  function selectProject(projectId: string) {
    setActiveProjectId(projectId);
    preferenceStorage.set("active-project-id", projectId);
  }

  async function deleteProject(projectId: string) {
    setProjectError(null);
    try {
      await apiRequest(`/projects/${projectId}`, { method: "DELETE" });
      setProjects((current) => {
        const nextProjects = current.filter((project) => project.id !== projectId);
        setActiveProjectId((currentProjectId) => {
          if (currentProjectId !== projectId) return currentProjectId;
          const nextProjectId = nextProjects[0]?.id ?? "";
          preferenceStorage.set("active-project-id", nextProjectId);
          return nextProjectId;
        });
        return nextProjects;
      });
    } catch (error) {
      setProjectError((error as Error).message);
    }
  }

  async function renameProject(projectId: string, name: string) {
    setProjectError(null);
    try {
      const updated = await apiRequest<ProjectRead>(`/projects/${projectId}`, {
        method: "PUT",
        body: JSON.stringify({ name }),
      });
      const project = toProjectSummary(updated);
      setProjects((current) =>
        current.map((item) => (item.id === project.id ? project : item)),
      );
    } catch (error) {
      setProjectError((error as Error).message);
    }
  }

  async function signOut() {
    await supabase?.auth.signOut();
    window.location.hash = "login";
  }

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
            onSelect={selectProject}
            onCreate={() => setShowCreateProject(true)}
            onDelete={deleteProject}
            onRename={renameProject}
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
            <button className="logout-button" type="button" onClick={signOut}>
              <LogOut size={16} /> Uitloggen
            </button>
          </div>
        </header>
        <RouteContent
          route={route}
          activeProject={activeProject}
          projectError={projectError}
          projectsLoading={projectsLoading}
          onCreateProject={() => setShowCreateProject(true)}
          brand={brand}
          locale={locale}
          onBrandChange={onBrandChange}
          onLocaleChange={onLocaleChange}
        />
      </main>
      {showCreateProject && (
        <CreateProjectDialog
          submitting={creatingProject}
          error={projectError}
          onClose={() => setShowCreateProject(false)}
          onSubmit={async (draft) => {
            setCreatingProject(true);
            setProjectError(null);
            try {
              const created = await apiRequest<ProjectRead>("/projects", {
                method: "POST",
                body: JSON.stringify(draft),
              });
              const project = toProjectSummary(created);
              setProjects((current) => [...current, project]);
              selectProject(project.id);
              setShowCreateProject(false);
            } catch (error) {
              setProjectError((error as Error).message);
            } finally {
              setCreatingProject(false);
            }
          }}
        />
      )}
    </div>
  );
}

function RouteContent({
  route,
  activeProject,
  projectError,
  projectsLoading,
  onCreateProject,
  brand,
  locale,
  onBrandChange,
  onLocaleChange,
}: {
  route: string;
  activeProject?: ProjectSummary;
  projectError: string | null;
  projectsLoading: boolean;
  onCreateProject: () => void;
  brand: BrandSettings;
  locale: Locale;
  onBrandChange: (brand: BrandSettings) => void;
  onLocaleChange: (locale: Locale) => void;
}) {
  if (!activeProject) {
    return (
      <div className="content">
        <section className="empty-state">
          <p className="eyebrow">Live setup</p>
          <h1>{projectsLoading ? "Projecten laden..." : "Maak je eerste project aan"}</h1>
          <p>
            {projectError ??
              "Voeg je website toe om crawls, WordPress-acties en Google-data live te testen."}
          </p>
          {!projectsLoading && (
            <button className="primary-button" type="button" onClick={onCreateProject}>
              Project aanmaken
            </button>
          )}
        </section>
      </div>
    );
  }

  if (route === "search-console")
    return <SearchConsolePage projectId={activeProject.id} />;
  if (route === "ga4") return <Ga4Page projectId={activeProject.id} />;
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
