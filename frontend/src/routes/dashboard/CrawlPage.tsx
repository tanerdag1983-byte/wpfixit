import { Activity, AlertTriangle, CheckCircle2, Link2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { apiRequest } from "../../lib/api";

type CrawlRun = {
  id: string;
  root_url: string;
  url_limit: number;
  state: string;
  page_count: number;
  created_at: string;
  completed_at?: string | null;
};

type CrawlIssue = {
  id: string;
  issue_type: string;
  severity: string;
  message: string;
};

type CrawlResults = {
  run: CrawlRun;
  pages: Array<{ id: string; url: string; status_code?: number | null }>;
  issues: CrawlIssue[];
};

export function CrawlPage({ projectId }: { projectId: string }) {
  const [filter, setFilter] = useState<"all" | "high">("all");
  const [runs, setRuns] = useState<CrawlRun[]>([]);
  const [results, setResults] = useState<CrawlResults | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const load = useCallback(async () => {
    const response = await apiRequest<{ items: CrawlRun[] }>(
      `/projects/${projectId}/crawls`,
    );
    setRuns(response.items);
    if (response.items[0]) {
      setResults(
        await apiRequest<CrawlResults>(
          `/projects/${projectId}/crawls/${response.items[0].id}`,
        ),
      );
    } else {
      setResults(null);
    }
  }, [projectId]);

  useEffect(() => {
    setMessage("");
    load().catch((error: unknown) =>
      setMessage(error instanceof Error ? error.message : "Crawls laden mislukt."),
    );
  }, [load]);

  async function startCrawl() {
    setBusy(true);
    setMessage("");
    try {
      await apiRequest(`/projects/${projectId}/crawls`, {
        method: "POST",
        body: JSON.stringify({ limit: 500 }),
      });
      await load();
      setMessage("De crawl is gestart en de resultaten zijn bijgewerkt.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Crawl starten mislukt.");
    } finally {
      setBusy(false);
    }
  }

  async function selectRun(run: CrawlRun) {
    try {
      setResults(
        await apiRequest<CrawlResults>(
          `/projects/${projectId}/crawls/${run.id}`,
        ),
      );
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Crawl laden mislukt.");
    }
  }

  const issues = results?.issues ?? [];
  const visibleIssues = issues.filter(
    (issue) => filter === "all" || issue.severity === "high",
  );
  const latest = results?.run;

  return (
    <section className="data-page crawl-page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Externe website-analyse</p>
          <h1>Technische crawl</h1>
          <p className="subtitle">
            Alle bereikbare links, technische fouten en veranderingen per run.
          </p>
        </div>
        <button
          className="sync-button"
          disabled={busy}
          onClick={startCrawl}
          type="button"
        >
          <Activity size={16} />
          {busy ? "Crawlen..." : "Nieuwe crawl"}
        </button>
      </div>

      <div className="crawl-status">
        <div>
          <CheckCircle2 size={20} />
          <span>
            <strong>
              {latest ? `Laatste crawl ${stateLabel(latest.state)}` : "Nog geen crawl"}
            </strong>
            <small>
              {latest ? formatDate(latest.created_at) : "Start de eerste analyse"}
            </small>
          </span>
        </div>
        <strong>{latest?.page_count ?? 0} pagina&apos;s</strong>
        <span>{issues.length} bevindingen</span>
        <span>{latest?.root_url ?? "Geen domein"}</span>
      </div>

      {message && <p className="settings-message">{message}</p>}

      <div className="data-grid">
        <section>
          <div className="section-heading">
            <div>
              <p className="eyebrow">Technische bevindingen</p>
              <h2>Wat verdient aandacht?</h2>
            </div>
            <div className="crawl-filters" aria-label="Issuefilter">
              <button
                className={filter === "all" ? "selected" : ""}
                onClick={() => setFilter("all")}
                type="button"
              >
                Alles
              </button>
              <button
                className={filter === "high" ? "selected" : ""}
                onClick={() => setFilter("high")}
                type="button"
              >
                Hoge impact
              </button>
            </div>
          </div>
          <div className="crawl-issue-list">
            {visibleIssues.length === 0 && (
              <p className="settings-empty">Geen bevindingen voor dit filter.</p>
            )}
            {visibleIssues.map((issue) => (
              <div className="crawl-issue" key={issue.id}>
                <span className={`issue-icon ${issue.severity}`}>
                  {issue.severity === "high" ? (
                    <AlertTriangle size={17} />
                  ) : (
                    <Link2 size={17} />
                  )}
                </span>
                <span>
                  <strong>{issueLabel(issue.issue_type)}</strong>
                  <small>{issue.message}</small>
                </span>
                <span className={`priority-tag ${issue.severity}`}>
                  {issue.severity === "high" ? "Hoog" : "Middel"}
                </span>
              </div>
            ))}
          </div>
        </section>

        <section>
          <div className="section-heading">
            <div>
              <p className="eyebrow">Historie</p>
              <h2>Recente crawls</h2>
            </div>
          </div>
          <div className="crawl-history">
            <div className="crawl-history-row header">
              <span>Gestart</span>
              <span>Status</span>
              <span>Pagina&apos;s</span>
              <span>Limiet</span>
            </div>
            {runs.map((run) => (
              <button
                className="crawl-history-row"
                onClick={() => selectRun(run)}
                type="button"
                key={run.id}
              >
                <strong>{formatDate(run.created_at)}</strong>
                <span className="crawl-complete">{stateLabel(run.state)}</span>
                <span>{run.page_count}</span>
                <span>{run.url_limit}</span>
              </button>
            ))}
          </div>
        </section>
      </div>
    </section>
  );
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("nl-NL", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function stateLabel(state: string) {
  return {
    completed: "voltooid",
    running: "actief",
    starting: "wordt gestart",
    failed: "mislukt",
    cancelled: "geannuleerd",
  }[state] ?? state;
}

function issueLabel(issueType: string) {
  return issueType.replaceAll("_", " ");
}
