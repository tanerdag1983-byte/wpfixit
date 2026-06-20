import { ArrowUpRight, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";

import { apiRequest } from "../../../lib/api";
import { useI18n } from "../../../features/preferences/useI18n";

type Recommendation = {
  id: string;
  wordpress_page_id: string;
  url: string;
  action_type: string;
  priority: string;
  action_title?: string;
  explanation?: string;
  recommendation: string;
  provider: string;
  model?: string | null;
  generation_status?: "ai" | "rules" | "fallback";
  fallback_reason?: string | null;
  approval_state: string;
};

export function ActionWorkspace({ projectId }: { projectId: string }) {
  const { t } = useI18n();
  const [items, setItems] = useState<Recommendation[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    let active = true;
    apiRequest<{ items: Recommendation[] }>(
      `/projects/${projectId}/recommendations?limit=10`,
    )
      .then((response) => {
        if (active) setItems(response.items);
      })
      .catch((error: unknown) => {
        if (active) {
          setMessage(
            error instanceof Error
              ? error.message
              : "Aanbevelingen laden mislukt.",
          );
        }
      });
    return () => {
      active = false;
    };
  }, [projectId]);

  async function generate() {
    setBusy(true);
    setMessage("");
    try {
      const response = await apiRequest<{ items: Recommendation[] }>(
        `/projects/${projectId}/recommendations/generate?limit=10`,
        { method: "POST" },
      );
      setItems(response.items);
      setMessage(generationMessage(response.items));
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
      await apiRequest(
        `/projects/${projectId}/recommendations/${item.id}/change-proposal`,
        {
          method: "POST",
        },
      );
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
            Nog geen opgeslagen aanbevelingen. Genereer ze eenmalig uit je
            WordPress-audit en verkeersdata.
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
              <strong>{recommendationTitle(item)}</strong>
              {item.explanation && (
                <span className="recommendation-explanation">
                  {item.explanation}
                </span>
              )}
              <small>
                {new URL(item.url).pathname} ·{" "}
                <span className="recommendation-provider">
                  {providerLabel(item)}
                </span>
              </small>
              {item.generation_status === "fallback" && item.fallback_reason && (
                <span className="recommendation-warning">
                  AI fallback: {item.fallback_reason}
                </span>
              )}
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
  if (item.generation_status === "fallback") return "Regels-engine · AI fallback";
  if (item.provider === "rules") return "Regels-engine";
  return item.model ? `${item.provider} · ${item.model}` : item.provider;
}

function generationMessage(items: Recommendation[]) {
  if (!items.length) {
    return "Er zijn nog geen pagina-audits om aanbevelingen voor te maken.";
  }

  const fallback = items.find((item) => item.generation_status === "fallback");
  if (fallback?.fallback_reason) {
    return `Aanbevelingen zijn opgeslagen. Let op: AI viel terug op regels (${fallback.fallback_reason}).`;
  }

  return "Aanbevelingen zijn als voorstel opgeslagen.";
}

function recommendationTitle(item: Recommendation) {
  if (item.action_title?.trim()) return item.action_title.trim();
  const labels: Record<string, string> = {
    seo_title: "Maak de SEO-title specifieker",
    meta_description: "Verbeter de meta description",
    canonical: "Controleer de canonical URL",
    noindex: "Controleer de indexeerbaarheid",
    content: "Verbeter de pagina-inhoud",
    internal_links: "Verbeter interne links",
    redirect: "Controleer redirect",
  };
  return labels[item.action_type] ?? readableSnippet(item.recommendation);
}

function readableSnippet(value: string) {
  return value
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 120);
}
