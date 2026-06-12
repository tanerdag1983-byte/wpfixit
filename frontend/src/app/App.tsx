import {
  Activity,
  ArrowUpRight,
  BarChart3,
  CheckCircle2,
  ChevronDown,
  LayoutDashboard,
  Search,
  Settings,
  Sparkles,
} from "lucide-react";

const metrics = [
  { label: "SEO health", value: "74", change: "+3 punten" },
  { label: "Organic clicks", value: "8.4K", change: "+12,6%" },
  { label: "Kansen", value: "18", change: "6 hoge impact" },
];

const priorities = [
  {
    score: 94,
    title: "Verbeter de snippet van /revisie",
    detail: "12.400 impressies · CTR 1,2% · positie 4,6",
  },
  {
    score: 87,
    title: "Verhoog conversie op /versnellingsbak",
    detail: "1.840 sessies · 0,6% conversie · dalend",
  },
  {
    score: 72,
    title: "Breid content uit voor automaat revisie",
    detail: "Positie 8,2 · hoge commerciële intentie",
  },
];

export function App() {
  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="Hoofdnavigatie">
        <a className="brand" href="/" aria-label="WP FixPilot home">
          <span>W</span>
          <strong>WP FixPilot</strong>
        </a>

        <nav>
          <a className="nav-item active" href="#overview">
            <LayoutDashboard size={18} />
            Overzicht
          </a>
          <a className="nav-item" href="#analytics">
            <BarChart3 size={18} />
            Analytics
          </a>
          <a className="nav-item" href="#actions">
            <CheckCircle2 size={18} />
            Acties
          </a>
          <a className="nav-item" href="#opportunities">
            <Sparkles size={18} />
            Kansen
          </a>
        </nav>

        <a className="nav-item settings-link" href="#settings">
          <Settings size={18} />
          Instellingen
        </a>
      </aside>

      <main className="workspace">
        <header className="topbar">
          <button className="project-switcher" type="button">
            <span className="project-mark">S</span>
            <span>
              <small>Project</small>
              shmtransmissie.nl
            </span>
            <ChevronDown size={16} />
          </button>

          <div className="topbar-actions">
            <label className="search-field">
              <Search size={16} />
              <span className="sr-only">Zoeken</span>
              <input placeholder="Zoek pagina of issue" />
            </label>
            <button className="sync-button" type="button">
              <Activity size={16} />
              Synchroniseren
            </button>
          </div>
        </header>

        <div className="content">
          <section className="page-heading">
            <div>
              <p className="eyebrow">SEO command center</p>
              <h1>WP FixPilot</h1>
              <p className="subtitle">
                Google-data, WordPress en crawlinzichten in één werkruimte.
              </p>
            </div>
            <div className="view-switcher" aria-label="Dashboardweergave">
              <button type="button">Analytics</button>
              <button type="button">Acties</button>
              <button className="selected" type="button">
                Hybride
              </button>
            </div>
          </section>

          <section className="metric-strip" aria-label="Belangrijkste statistieken">
            {metrics.map((metric) => (
              <div className="metric" key={metric.label}>
                <span>{metric.label}</span>
                <strong>{metric.value}</strong>
                <small>{metric.change}</small>
              </div>
            ))}
            <div className="sync-status">
              <span className="status-dot" />
              Alle bronnen actief
              <small>8 minuten geleden bijgewerkt</small>
            </div>
          </section>

          <section className="workspace-grid">
            <div className="trend-panel">
              <div className="section-heading">
                <div>
                  <p className="eyebrow">Organische prestaties</p>
                  <h2>Clicks en conversies</h2>
                </div>
                <button className="text-button" type="button">
                  Laatste 30 dagen <ChevronDown size={14} />
                </button>
              </div>

              <div className="chart" aria-label="Voorbeeldgrafiek">
                <div className="chart-lines" />
                <svg viewBox="0 0 760 260" preserveAspectRatio="none">
                  <path
                    className="area"
                    d="M0 220 C70 180 100 210 165 160 S290 185 350 112 S470 145 530 76 S650 108 760 34 L760 260 L0 260 Z"
                  />
                  <path
                    className="primary-line"
                    d="M0 220 C70 180 100 210 165 160 S290 185 350 112 S470 145 530 76 S650 108 760 34"
                  />
                  <path
                    className="secondary-line"
                    d="M0 238 C90 225 145 230 205 210 S330 218 400 180 S525 192 590 150 S690 162 760 116"
                  />
                </svg>
                <div className="chart-labels">
                  <span>14 mei</span>
                  <span>21 mei</span>
                  <span>28 mei</span>
                  <span>4 juni</span>
                  <span>12 juni</span>
                </div>
              </div>
            </div>

            <div className="priority-panel">
              <div className="section-heading">
                <div>
                  <p className="eyebrow">Vandaag</p>
                  <h2>Topprioriteiten</h2>
                </div>
                <button className="icon-button" type="button" aria-label="Open acties">
                  <ArrowUpRight size={18} />
                </button>
              </div>

              <div className="priority-list">
                {priorities.map((priority) => (
                  <button className="priority-row" type="button" key={priority.title}>
                    <span className="score">{priority.score}</span>
                    <span>
                      <strong>{priority.title}</strong>
                      <small>{priority.detail}</small>
                    </span>
                    <ArrowUpRight size={16} />
                  </button>
                ))}
              </div>
            </div>
          </section>
        </div>
      </main>
    </div>
  );
}

