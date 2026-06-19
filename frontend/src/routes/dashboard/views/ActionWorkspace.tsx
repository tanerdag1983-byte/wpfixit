import { ArrowUpRight, Sparkles } from "lucide-react";
import { useState } from "react";

import { apiRequest } from "../../../lib/api";
import { useI18n } from "../../../features/preferences/useI18n";

type Recommendation = {
  id: string;
  wordpress_page_id: string;
  url: string;
  action_type: string;
  priority: string;
  recommendation: string;
  provider: string;
  model?: string | null;
  approval_state: string;
};

export function ActionWorkspace({ projectId }: { projectId: string }) {
  const { t } = useI18n();
  const [items, setItems] = useState<Recommendation[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  async function generate() {
    setBusy(true);
    setMessage("");
    try {
      const response = await apiRequest<{ items: Recommendation[] }>(
        `/projects/${projectId}/recommendations/generate?limit=10`,
        { method: "POST" },
      );
      setItems(response.items);
      setMessage(
        response.items.length
          ? "Aanbevelingen zijn als voorstel opgeslagen."
          : "Er zijn nog geen pagina-audits om aanbevelingen voor te maken.",
      );
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Genereren mislukt.");
    } finally {
      setBusy(false);
    }
  }

  async function createProposal(item: Recommendation) {
    setBusy(true);
    setMessage("");
    try {
      await apiRequest(`/projects/${projectId}/change-proposals`, {
        method: "POST",
        body: JSON.stringify({
          wordpress_page_id: item.wordpress_page_id,
          recommendation_id: item.id,
          change_type: item.action_type,
          before_value: "",
          after_value: item.recommendation,
        }),
      });
      window.location.hash = "publishing";
    } catch (error) {
      setMessage(
        error instanceof Error
          ? error.message
          : "Wijzigingsvoorstel maken mislukt.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="dashboard-view">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Action workspace</p>
          <h1>{t("actionHeading")}</h1>
          <p className="subtitle">
            Gegenereerd uit WordPress-audits en beschikbare verkeersdata.
          </p>
        </div>
        <button
          className="sync-button"
          disabled={busy}
          onClick={generate}
          type="button"
        >
          <Sparkles size={16} />
          {busy ? "Genereren..." : "Aanbevelingen genereren"}
        </button>
      </div>
      {message && <p className="settings-message">{message}</p>}
      <div className="action-workspace-list">
        {items.length === 0 && (
          <p className="settings-empty">
            Genereer aanbevelingen om de echte projectresultaten te bekijken.
          </p>
        )}
        {items.map((item, index) => (
          <button
            disabled={busy}
            key={item.id}
            onClick={() => createProposal(item)}
            type="button"
          >
            <span className="priority-number">{100 - index * 8}</span>
            <span>
              <strong>{item.recommendation}</strong>
              <small>
                {new URL(item.url).pathname} ·{" "}
                <span className="recommendation-provider">
                  {providerLabel(item)}
                </span>
              </small>
            </span>
            <span className={`priority-tag ${item.priority}`}>
              {item.approval_state === "proposed" ? "Voorstel" : item.approval_state}
            </span>
            <ArrowUpRight size={17} />
          </button>
        ))}
      </div>
    </section>
  );
}

function providerLabel(item: Recommendation) {
  if (item.provider === "rules") return "Regels-engine";
  return item.model ? `${item.provider} · ${item.model}` : item.provider;
}
