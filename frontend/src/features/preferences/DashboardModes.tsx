import { useState } from "react";

import { defaultBrand } from "../../config/brand";
import { useI18n } from "./useI18n";
import { ActionWorkspace } from "../../routes/dashboard/views/ActionWorkspace";
import { AnalyticsConsole } from "../../routes/dashboard/views/AnalyticsConsole";
import { HybridCommandCenter } from "../../routes/dashboard/views/HybridCommandCenter";
import { preferenceStorage } from "./storage";

export type DashboardView = "analytics" | "action" | "hybrid";

export function DashboardModes({
  savedView,
  brandName = defaultBrand.name,
  projectId,
}: {
  savedView?: DashboardView;
  brandName?: string;
  projectId: string;
}) {
  const [view, setView] = useState<DashboardView>(
    savedView ??
      (preferenceStorage.get("dashboard-view") as DashboardView | null) ??
      "hybrid",
  );
  const { t } = useI18n();
  const select = (next: DashboardView) => {
    setView(next);
    preferenceStorage.set("dashboard-view", next);
  };

  return (
    <>
      <div className="view-switcher mode-switcher" aria-label="Dashboardweergave">
        <button className={view === "analytics" ? "selected" : ""} onClick={() => select("analytics")} type="button">{t("analyticsView")}</button>
        <button className={view === "action" ? "selected" : ""} onClick={() => select("action")} type="button">{t("actionView")}</button>
        <button className={view === "hybrid" ? "selected" : ""} onClick={() => select("hybrid")} type="button">{t("hybridView")}</button>
      </div>
      {view === "analytics" && <AnalyticsConsole />}
      {view === "action" && <ActionWorkspace projectId={projectId} />}
      {view === "hybrid" && <HybridCommandCenter brandName={brandName} />}
    </>
  );
}
