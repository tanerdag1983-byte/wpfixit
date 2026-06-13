import { ArrowUpRight, MousePointerClick, Search, TrendingUp } from "lucide-react";

const metrics = [
  { label: "Clicks", value: "8.4K", change: "+12,6%" },
  { label: "Impressies", value: "312K", change: "+18,2%" },
  { label: "CTR", value: "2,7%", change: "-0,2%" },
  { label: "Gem. positie", value: "8,4", change: "+1,3" },
];

const queries = [
  ["transmissie revisie", "12.4K", "1,2%", "4,6"],
  ["automaat revisie", "8.9K", "2,8%", "6,1"],
  ["versnellingsbak specialist", "6.2K", "3,4%", "5,3"],
  ["automatische transmissie", "5.7K", "1,9%", "9,2"],
];

export function SearchConsolePage() {
  return (
    <section className="data-page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Google-data</p>
          <h1>Search Console</h1>
          <p className="subtitle">
            Zoekprestaties, CTR-kansen en posities per pagina en query.
          </p>
        </div>
        <button className="sync-button" type="button">
          <TrendingUp size={16} />
          Data synchroniseren
        </button>
      </div>

      <div className="data-metrics">
        {metrics.map((metric) => (
          <div key={metric.label}>
            <span>{metric.label}</span>
            <strong>{metric.value}</strong>
            <small>{metric.change}</small>
          </div>
        ))}
      </div>

      <div className="data-grid">
        <section className="search-trend">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Laatste 30 dagen</p>
              <h2>Clicks en impressies</h2>
            </div>
            <MousePointerClick size={19} />
          </div>
          <div className="mini-chart">
            <svg viewBox="0 0 700 250" preserveAspectRatio="none">
              <path
                className="area"
                d="M0 210 C90 180 120 196 180 148 S310 170 365 105 S500 130 555 62 S650 85 700 28 L700 250 L0 250 Z"
              />
              <path
                className="primary-line"
                d="M0 210 C90 180 120 196 180 148 S310 170 365 105 S500 130 555 62 S650 85 700 28"
              />
            </svg>
          </div>
        </section>

        <section className="query-panel">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Zoekwoorden</p>
              <h2>Topqueries</h2>
            </div>
            <Search size={18} />
          </div>
          <div className="query-table">
            <div className="query-row header">
              <span>Query</span>
              <span>Impressies</span>
              <span>CTR</span>
              <span>Positie</span>
            </div>
            {queries.map(([query, impressions, ctr, position]) => (
              <button className="query-row" type="button" key={query}>
                <strong>{query}</strong>
                <span>{impressions}</span>
                <span>{ctr}</span>
                <span>
                  {position} <ArrowUpRight size={13} />
                </span>
              </button>
            ))}
          </div>
        </section>
      </div>
    </section>
  );
}

