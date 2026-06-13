import { Activity, AlertTriangle, CheckCircle2, Link2 } from "lucide-react";
import { useState } from "react";

const issues = [
  {
    title: "Gebroken interne links",
    detail: "31 links op 18 pagina's",
    severity: "high",
  },
  {
    title: "Canonical-conflicten",
    detail: "9 pagina's verwijzen naar een andere URL",
    severity: "high",
  },
  {
    title: "Dubbele descriptions",
    detail: "42 pagina's delen dezelfde description",
    severity: "medium",
  },
  {
    title: "Mogelijke orphan pages",
    detail: "14 pagina's zonder inkomende interne link",
    severity: "medium",
  },
];

const history = [
  ["Vandaag, 09:42", "Voltooid", "2.184", "96"],
  ["6 juni, 14:10", "Voltooid", "2.147", "103"],
  ["30 mei, 08:55", "Voltooid", "2.109", "111"],
];

export function CrawlPage() {
  const [filter, setFilter] = useState<"all" | "high">("all");
  const visibleIssues = issues.filter(
    (issue) => filter === "all" || issue.severity === "high",
  );

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
        <button className="sync-button" type="button">
          <Activity size={16} />
          Nieuwe crawl
        </button>
      </div>

      <div className="crawl-status">
        <div>
          <CheckCircle2 size={20} />
          <span>
            <strong>Laatste crawl voltooid</strong>
            <small>Vandaag om 09:58 · 16 minuten</small>
          </span>
        </div>
        <strong>2.184 pagina&apos;s</strong>
        <span>96 bevindingen</span>
        <span>37 nieuwe URL&apos;s</span>
      </div>

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
            {visibleIssues.map((issue) => (
              <button className="crawl-issue" type="button" key={issue.title}>
                <span className={`issue-icon ${issue.severity}`}>
                  {issue.severity === "high" ? (
                    <AlertTriangle size={17} />
                  ) : (
                    <Link2 size={17} />
                  )}
                </span>
                <span>
                  <strong>{issue.title}</strong>
                  <small>{issue.detail}</small>
                </span>
                <span className={`priority-tag ${issue.severity}`}>
                  {issue.severity === "high" ? "Hoog" : "Middel"}
                </span>
              </button>
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
              <span>Issues</span>
            </div>
            {history.map(([started, state, pages, findingCount]) => (
              <button className="crawl-history-row" type="button" key={started}>
                <strong>{started}</strong>
                <span className="crawl-complete">{state}</span>
                <span>{pages}</span>
                <span>{findingCount}</span>
              </button>
            ))}
          </div>
        </section>
      </div>
    </section>
  );
}
