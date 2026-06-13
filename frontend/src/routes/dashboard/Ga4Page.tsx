import { Activity, ArrowUpRight, CircleDollarSign, Users } from "lucide-react";

const metrics = [
  { label: "Sessies", value: "12.1K", change: "+8,1%" },
  { label: "Gebruikers", value: "9.7K", change: "+6,4%" },
  { label: "Engagement", value: "63%", change: "+2,8%" },
  { label: "Conversies", value: "384", change: "+4,3%" },
];

const sources = [
  ["google / organic", "7.840", "66%", "241"],
  ["(direct) / (none)", "2.180", "58%", "72"],
  ["bing / organic", "740", "61%", "28"],
  ["referral / partner", "516", "70%", "24"],
];

export function Ga4Page() {
  return (
    <section className="data-page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Gedrag en resultaat</p>
          <h1>Google Analytics 4</h1>
          <p className="subtitle">
            Verkeer, engagement, conversies en omzet per pagina en kanaal.
          </p>
        </div>
        <button className="sync-button" type="button">
          <Activity size={16} />
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
        <section>
          <div className="section-heading">
            <div>
              <p className="eyebrow">Laatste 30 dagen</p>
              <h2>Sessies en conversies</h2>
            </div>
            <Users size={19} />
          </div>
          <div className="mini-chart">
            <svg viewBox="0 0 700 250" preserveAspectRatio="none">
              <path
                className="area"
                d="M0 205 C55 185 95 198 145 165 S245 180 300 125 S410 146 470 95 S585 112 635 58 S680 65 700 31 L700 250 L0 250 Z"
              />
              <path
                className="primary-line"
                d="M0 205 C55 185 95 198 145 165 S245 180 300 125 S410 146 470 95 S585 112 635 58 S680 65 700 31"
              />
              <path
                className="secondary-line"
                d="M0 230 C90 218 160 222 225 205 S350 210 420 180 S550 192 620 155 S670 150 700 130"
              />
            </svg>
          </div>
        </section>

        <section className="query-panel">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Acquisitie</p>
              <h2>Verkeersbronnen</h2>
            </div>
            <CircleDollarSign size={19} />
          </div>
          <div className="query-table">
            <div className="query-row header">
              <span>Bron / medium</span>
              <span>Sessies</span>
              <span>Engagement</span>
              <span>Conversies</span>
            </div>
            {sources.map(([source, sessions, engagement, conversions]) => (
              <button className="query-row" type="button" key={source}>
                <strong>{source}</strong>
                <span>{sessions}</span>
                <span>{engagement}</span>
                <span>
                  {conversions} <ArrowUpRight size={13} />
                </span>
              </button>
            ))}
          </div>
        </section>
      </div>
    </section>
  );
}
