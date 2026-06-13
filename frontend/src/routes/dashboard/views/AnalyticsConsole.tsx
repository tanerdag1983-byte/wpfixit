import { dashboardData } from "../dashboardData";
import { useI18n } from "../../../features/preferences/useI18n";

export function AnalyticsConsole() {
  const { t } = useI18n();
  return (
    <section className="dashboard-view">
      <p className="eyebrow">Analytics console</p>
      <h1>{t("analyticsHeading")}</h1>
      <p className="subtitle">
        Zoekzichtbaarheid, verkeer en conversies in één rustige dataweergave.
      </p>
      <MetricStrip />
      <div className="analytics-console-grid">
        <section>
          <h2>Clicks en conversies</h2>
          <TrendChart />
          <table className="sr-only">
            <caption>Clicks en conversies per week</caption>
            <tbody>
              <tr><th>Week 1</th><td>1.820 clicks</td><td>72 conversies</td></tr>
              <tr><th>Week 2</th><td>2.140 clicks</td><td>89 conversies</td></tr>
            </tbody>
          </table>
        </section>
        <section>
          <h2>Top queries</h2>
          <div className="compact-data-list">
            {dashboardData.queries.map(([query, impressions, ctr]) => (
              <div key={query}>
                <strong>{query}</strong><span>{impressions}</span><span>{ctr}</span>
              </div>
            ))}
          </div>
          <h2 className="subsection-title">Verkeersbronnen</h2>
          <div className="compact-data-list">
            {dashboardData.sources.map(([source, sessions, conversions]) => (
              <div key={source}>
                <strong>{source}</strong><span>{sessions}</span><span>{conversions}</span>
              </div>
            ))}
          </div>
        </section>
      </div>
    </section>
  );
}

export function MetricStrip() {
  return (
    <div className="data-metrics">
      {dashboardData.metrics.map((metric) => (
        <div key={metric.label}>
          <span>{metric.label}</span><strong>{metric.value}</strong>
          <small>{metric.change}</small>
        </div>
      ))}
    </div>
  );
}

export function TrendChart() {
  return (
    <div className="mini-chart" aria-label="Clicks en conversies trend">
      <svg viewBox="0 0 700 250" preserveAspectRatio="none">
        <path className="area" d="M0 205 C90 185 120 195 180 150 S310 175 370 112 S500 130 565 75 S650 80 700 31 L700 250 L0 250 Z" />
        <path className="primary-line" d="M0 205 C90 185 120 195 180 150 S310 175 370 112 S500 130 565 75 S650 80 700 31" />
        <path className="secondary-line" d="M0 230 C120 220 180 225 250 200 S410 205 480 170 S610 178 700 125" />
      </svg>
    </div>
  );
}
