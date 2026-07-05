import { ArrowDown, ArrowUpRight, SlidersHorizontal } from "lucide-react";
import { useEffect, useState } from "react";
import { apiRequest } from "../../lib/api";

interface PriorityItem {
  url: string;
  title: string;
  seo_score: number;
  clicks: number | null;
  impressions: number | null;
  ctr: number | null;
  average_position: number | null;
  sessions: number | null;
  conversions: number | null;
  trend: string | null;
  priority_score: number;
  confidence: number;
  components: Record<string, unknown>;
  action: string;
  evidence: Array<Record<string, unknown>>;
}

export function PriorityPage({ projectId }: { projectId: string }) {
  const [items, setItems] = useState<PriorityItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchPriorities() {
      try {
        setLoading(true);
        const response = await apiRequest<{ items: PriorityItem[] }>(
          `/projects/${projectId}/seo-priority-score?minimum_score=0&limit=100`,
        );
        setItems(response.items);
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Er is iets misgegaan");
        console.error("Failed to fetch priorities:", err);
      } finally {
        setLoading(false);
      }
    }
    void fetchPriorities();
  }, [projectId]);

  if (loading) {
    return (
      <section className="data-page priority-page">
        <p>Laden...</p>
      </section>
    );
  }

  if (error) {
    return (
      <section className="data-page priority-page">
        <p style={{ color: "red" }}>Fout: {error}</p>
      </section>
    );
  }

  return (
    <section className="data-page priority-page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Gecombineerde beslislaag</p>
          <h1>SEO-prioriteiten</h1>
          <p className="subtitle">
            Eén ranglijst op basis van SEO-kwaliteit, zichtbaarheid en resultaat.
          </p>
        </div>
        <button className="secondary-button priority-filter" type="button">
          <SlidersHorizontal size={15} />
          Filters
        </button>
      </div>

      {items.length === 0 ? (
        <p>Geen prioriteiten gevonden.</p>
      ) : (
        <div className="priority-table">
          <div className="priority-table-row header">
            <span>Score</span>
            <span>Pagina</span>
            <span>Zoekprestatie</span>
            <span>Resultaat</span>
            <span>Actie</span>
          </div>
          {items.map((item) => {
            const trendValue = item.trend ? parseFloat(item.trend) : 0;
            const trendDirection = trendValue < 0 ? "down" : "up";
            const searchDisplay =
              item.impressions !== null && item.ctr !== null
                ? `${item.impressions.toLocaleString("nl-NL")} impressies · ${(item.ctr * 100).toLocaleString("nl-NL", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}% CTR`
                : item.impressions !== null
                  ? `${item.impressions.toLocaleString("nl-NL")} impressies`
                  : item.average_position !== null
                    ? `positie ${item.average_position.toLocaleString("nl-NL", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}`
                    : "Geen data";
            const trafficDisplay =
              item.sessions !== null || item.conversions !== null
                ? `${(item.sessions ?? 0).toLocaleString("nl-NL")} sessies${item.conversions ? ` · ${item.conversions.toLocaleString("nl-NL")} conversies` : ""}`
                : "Geen data";

            return (
              <button className="priority-table-row" type="button" key={item.url}>
                <span className="priority-number">
                  {Math.round(item.priority_score)}
                </span>
                <span className="priority-page-name">
                  <strong>{item.title}</strong>
                  <small>
                    {item.url} · {Math.round(item.seo_score)} SEO
                  </small>
                </span>
                <span>{searchDisplay}</span>
                <span>
                  {trafficDisplay}
                  {item.trend && (
                    <small className={`trend-${trendDirection}`}>
                      {trendDirection === "down" ? (
                        <ArrowDown size={12} />
                      ) : (
                        <ArrowUpRight size={12} />
                      )}
                      {item.trend}
                    </small>
                  )}
                </span>
                <span className="priority-action">
                  {item.action}
                  <ArrowUpRight size={15} />
                </span>
              </button>
            );
          })}
        </div>
      )}
    </section>
  );
}
