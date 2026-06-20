import { ArrowUpRight, Sparkles } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

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
  priority_score?: number | null;
  approval_state: string;
};

type GenerationJob = {
  id: string;
  state: "queued" | "running" | "completed" | "failed" | "cancelled";
  progress: number;
  total?: number | null;
  completed?: number | null;
  error_message?: string | null;
};

export function ActionWorkspace({ projectId }: { projectId: string }) {
  const { t } = useI18n();
  const [items, setItems] = useState<Recommendation[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [job, setJob] = useState<GenerationJob | null>(null);

  const loadItems = useCallback(async () => {
    const response = await apiRequest<{ items: Recommendation[] }>(
      `/projects/${projectId}/recommendations?limit=10`,
    );
    setItems(response.items);
    return response.items;
  }, [projectId]);

  const monitorJob = useCallback(
    async (jobId: string) => {
      setBusy(true);
      setMessage("Aanbevelingen worden op de achtergrond gegenereerd.");
      while (true) {
        const response = await apiRequest<{ job: GenerationJob }>(
          `/projects/${projectId}/recommendations/generation-jobs/${jobId}`,
        );
        setJob(response.job);
        if (response.job.state === "completed") {
          const nextItems = await loadItems();
          setMessage(generationMessage(nextItems));
          setBusy(false);
          return;
        }
        if (
          response.job.state === "failed" ||
          response.job.state === "cancelled"
        ) {
          setMessage(
            response.job.error_message ?? "Aanbevelingen genereren is gestopt.",
          );
          setBusy(false);
          return;
        }
        await delay(2_000);
      }
    },
    [loadItems, projectId],
  );

  useEffect(() => {
    let active = true;
    loadItems()
      .then(async () => {
        const response = await apiRequest<{ job: GenerationJob | null }>(
          `/projects/${projectId}/recommendations/generation-jobs/latest`,
        );
        if (!active || !response.job) return;
        setJob(response.job);
        if (isActiveJob(response.job)) {
          void monitorJob(response.job.id);
        }
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
  }, [loadItems, monitorJob, projectId]);

  async function generate() {
    setBusy(true);
    setMessage("");
    try {
      const response = await apiRequest<{ job: GenerationJob }>(
        `/projects/${projectId}/recommendations/generate?limit=10`,
        { method: "POST" },
      );
      setJob(response.job);
      await monitorJob(response.job.id);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Genereren mislukt.");
      setBusy(false);
    } finally {
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
      <p className="score-help">
        De rode getallen zijn prioriteitsscores van 0 tot 100. Hoe hoger de
        score, hoe eerder deze pagina aandacht verdient. Genereren maakt per
        klik maximaal 10 voorstellen voor de pagina&apos;s met de hoogste
        prioriteit.
      </p>
      {busy && (
        <p className="settings-message">
          We genereren nu maximaal 10 pagina&apos;s met de hoogste prioriteit.
          Met AI kan dit even duren. Je kunt de pagina vernieuwen; de job loopt
          op de server door.
          {job && ` Voortgang: ${job.completed ?? 0}/${job.total ?? 10}.`}
        </p>
      )}
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
            <span className="priority-number">{priorityScore(item, index)}</span>
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

function priorityScore(item: Recommendation, index: number) {
  return typeof item.priority_score === "number"
    ? item.priority_score
    : 100 - index * 8;
}

function isActiveJob(job: GenerationJob) {
  return job.state === "queued" || job.state === "running";
}

function delay(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
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
