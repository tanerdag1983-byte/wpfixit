import { ArrowDown, ArrowUpRight, SlidersHorizontal } from "lucide-react";

const pages = [
  {
    score: "94",
    title: "Transmissie revisie",
    url: "/revisie",
    seo: "48 SEO",
    search: "12.400 impressies · 1,2% CTR",
    traffic: "1.840 sessies · 11 conversies",
    trend: "-22%",
    action: "Verbeter snippet en herstel conversieverlies",
  },
  {
    score: "87",
    title: "Automatische versnellingsbak",
    url: "/automatische-versnellingsbak",
    seo: "61 SEO",
    search: "8.900 impressies · 2,1% CTR",
    traffic: "1.210 sessies · 9 conversies",
    trend: "-9%",
    action: "Verdiep content en maak de CTA specifieker",
  },
  {
    score: "72",
    title: "Automaat revisie",
    url: "/automaat-revisie",
    seo: "74 SEO",
    search: "7.100 impressies · positie 8,2",
    traffic: "640 sessies · 14 conversies",
    trend: "+4%",
    action: "Voeg interne links vanaf sterke servicepagina's toe",
  },
];

export function PriorityPage() {
  return (
    <section className="data-page priority-page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Gecombineerde beslislaag</p>
          <h1>SEO-prioriteiten</h1>
          <p className="subtitle">
            Eén ranglijst op basis van SEO-kwaliteit, zichtbaarheid en resultaat.
          </p>
        </div>
        <button className="secondary-button priority-filter" type="button">
          <SlidersHorizontal size={15} />
          Filters
        </button>
      </div>

      <div className="priority-table">
        <div className="priority-table-row header">
          <span>Score</span>
          <span>Pagina</span>
          <span>Zoekprestatie</span>
          <span>Resultaat</span>
          <span>Actie</span>
        </div>
        {pages.map((page) => (
          <button className="priority-table-row" type="button" key={page.url}>
            <span className="priority-number">{page.score}</span>
            <span className="priority-page-name">
              <strong>{page.title}</strong>
              <small>
                {page.url} · {page.seo}
              </small>
            </span>
            <span>{page.search}</span>
            <span>
              {page.traffic}
              <small
                className={page.trend.startsWith("-") ? "trend-down" : "trend-up"}
              >
                {page.trend.startsWith("-") ? (
                  <ArrowDown size={12} />
                ) : (
                  <ArrowUpRight size={12} />
                )}
                {page.trend}
              </small>
            </span>
            <span className="priority-action">
              {page.action}
              <ArrowUpRight size={15} />
            </span>
          </button>
        ))}
      </div>
    </section>
  );
}
