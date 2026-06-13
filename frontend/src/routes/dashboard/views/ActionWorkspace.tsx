import { ArrowUpRight } from "lucide-react";

import { useI18n } from "../../../features/preferences/useI18n";
import { dashboardData } from "../dashboardData";

export function ActionWorkspace() {
  const { t } = useI18n();
  return (
    <section className="dashboard-view">
      <p className="eyebrow">Action workspace</p>
      <h1>{t("actionHeading")}</h1>
      <p className="subtitle">
        Gesorteerd op verwachte impact, met bewijs en een concrete vervolgstap.
      </p>
      <div className="action-workspace-list">
        {dashboardData.priorities.map((priority) => (
          <button type="button" key={priority.title}>
            <span className="priority-number">{priority.score}</span>
            <span>
              <strong>{priority.title}</strong>
              <small>{priority.detail}</small>
            </span>
            <span className="priority-tag high">Hoge impact</span>
            <ArrowUpRight size={17} />
          </button>
        ))}
      </div>
    </section>
  );
}
