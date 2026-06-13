import { Search } from "lucide-react";
import { useMemo, useState } from "react";

export type AuditPageRow = {
  id: string;
  title: string;
  url: string;
  status: string;
  pageType: string;
  priority: string;
  score: number;
};

export function AuditPagesTable({ pages }: { pages: AuditPageRow[] }) {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("all");
  const [pageType, setPageType] = useState("all");
  const [priority, setPriority] = useState("all");
  const [maxScore, setMaxScore] = useState("100");

  const filteredPages = useMemo(
    () =>
      pages.filter((page) => {
        const haystack = `${page.title} ${page.url}`.toLowerCase();
        return (
          haystack.includes(query.trim().toLowerCase()) &&
          (status === "all" || page.status === status) &&
          (pageType === "all" || page.pageType === pageType) &&
          (priority === "all" || page.priority === priority) &&
          page.score <= Number(maxScore)
        );
      }),
    [maxScore, pageType, pages, priority, query, status],
  );

  return (
    <section className="audit-section">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Pagina-inzichten</p>
          <h2>Auditresultaten</h2>
        </div>
        <span className="result-count">{filteredPages.length} resultaten</span>
      </div>

      <div className="filter-bar">
        <label className="table-search">
          <span className="sr-only">Pagina zoeken</span>
          <Search size={16} />
          <input
            aria-label="Pagina zoeken"
            placeholder="Zoek titel of URL"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
        <FilterSelect
          label="Status"
          value={status}
          onChange={setStatus}
          options={["all", "publish", "draft", "private"]}
        />
        <FilterSelect
          label="Paginatype"
          value={pageType}
          onChange={setPageType}
          options={["all", "service", "page", "blog", "homepage"]}
        />
        <FilterSelect
          label="Prioriteit"
          value={priority}
          onChange={setPriority}
          options={["all", "critical", "high", "medium", "low"]}
        />
        <label>
          <span>Maximale score</span>
          <select
            aria-label="Maximale score"
            value={maxScore}
            onChange={(event) => setMaxScore(event.target.value)}
          >
            {[100, 90, 80, 70, 60, 50].map((score) => (
              <option key={score} value={score}>
                {score}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="audit-table-wrap">
        <table className="audit-table">
          <thead>
            <tr>
              <th>Pagina</th>
              <th>Type</th>
              <th>Status</th>
              <th>Prioriteit</th>
              <th>Score</th>
            </tr>
          </thead>
          <tbody>
            {filteredPages.map((page) => (
              <tr key={page.id}>
                <td>
                  <strong>{page.title}</strong>
                  <small>{page.url}</small>
                </td>
                <td>{page.pageType}</td>
                <td>{page.status}</td>
                <td>
                  <span className={`priority-tag ${page.priority}`}>
                    {page.priority}
                  </span>
                </td>
                <td>
                  <span className="table-score">{page.score}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {filteredPages.length === 0 && (
          <div className="empty-state">Geen pagina's gevonden.</div>
        )}
      </div>
    </section>
  );
}

function FilterSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: string[];
}) {
  return (
    <label>
      <span>{label}</span>
      <select
        aria-label={label}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        {options.map((option) => (
          <option key={option} value={option}>
            {option === "all" ? "Alle" : option}
          </option>
        ))}
      </select>
    </label>
  );
}

