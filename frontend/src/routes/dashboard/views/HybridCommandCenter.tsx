import { ArrowUpRight } from "lucide-react";

import { useI18n } from "../../../features/preferences/useI18n";
import { dashboardData } from "../dashboardData";
import { MetricStrip, TrendChart } from "./AnalyticsConsole";

export function HybridCommandCenter({ brandName }: { brandName: string }) {
  const { t } = useI18n();
  return (
    <section className="dashboard-view">
      <p className="eyebrow">{t("hybridHeading")}</p>
      <h1>{brandName}</h1>
      <p className="subtitle">
        Data en acties naast elkaar voor dagelijkse SEO-beslissingen.
      </p>
      <MetricStrip />
      <div className="workspace-grid">
        <section>
          <h2>Organische prestaties</h2>
          <TrendChart />
        </section>
        <section>
          <h2>Topprioriteiten</h2>
          <div className="priority-list">
            {dashboardData.priorities.map((priority) => (
              <button className="priority-row" type="button" key={priority.title}>
                <span className="score">{priority.score}</span>
                <span><strong>{priority.title}</strong><small>{priority.detail}</small></span>
                <ArrowUpRight size={16} />
              </button>
            ))}
          </div>
        </section>
      </div>
    </section>
  );
}
