import { useCallback, useEffect, useState } from "react";
import { ArrowUpRight, Sparkles } from "lucide-react";

import { apiRequest } from "../../lib/api";

type KeywordOpportunity = {
  id: string;
  keyword: string;
  search_volume: number | null;
  cpc: number | string | null;
  competition_level: string | null;
  keyword_difficulty: number | null;
  intent: string | null;
  target_url: string | null;
  recommended_action: string | null;
  source: string;
};

type OpportunityResponse = {
  items: KeywordOpportunity[];
};

export function OpportunitiesPage({ projectId }: { projectId: string }) {
  const [items, setItems] = useState<KeywordOpportunity[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [message, setMessage] = useState("");

  const loadItems = useCallback(async () => {
    const response = await apiRequest<OpportunityResponse>(
      `/projects/${projectId}/keyword-opportunities`,
    );
    setItems(response.items);
  }, [projectId]);

  useEffect(() => {
    let active = true;
    setLoading(true);
    loadItems()
      .catch((error) => {
        if (active) {
          setMessage(
            error instanceof Error
              ? error.message
              : "Zoekwoordkansen laden mislukt.",
          );
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [loadItems]);

  async function syncOpportunities() {
    setSyncing(true);
    setMessage("DataForSEO onderzoekt nieuwe zoekwoordkansen. Dit kan even duren.");
    try {
      const response = await apiRequest<{ synced: number }>(
        `/projects/${projectId}/sync-keyword-opportunities`,
        { method: "POST" },
      );
      await loadItems();
      setMessage(
        `${response.synced} zoekwoordkans${response.synced === 1 ? "" : "en"} bijgewerkt.`,
      );
    } catch (error) {
      setMessage(
        error instanceof Error
          ? error.message
          : "Nieuwe zoekwoordkansen ophalen mislukt.",
      );
    } finally {
      setSyncing(false);
    }
  }

  return (
    <section className="data-page opportunity-page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Onderbouwde aanbevelingen</p>
          <h1>Kansen</h1>
          <p className="subtitle">
            Live zoekwoordmogelijkheden uit DataForSEO, gekoppeld aan je
            bestaande WordPress-pagina&apos;s.
          </p>
        </div>
        <button
          className="sync-button"
          disabled={syncing}
          onClick={syncOpportunities}
          type="button"
        >
          <Sparkles size={16} />
          {syncing ? "Kansen ophalen..." : "Nieuwe kansen ophalen"}
        </button>
      </div>

      {message && <p className="settings-message">{message}</p>}
      {loading && <p className="settings-empty">Zoekwoordkansen laden...</p>}
      {!loading && items.length === 0 && (
        <p className="settings-empty">
          Nog geen live zoekwoordkansen. Koppel DataForSEO bij Instellingen en
          haal daarna de eerste kansen op.
        </p>
      )}

      <div className="opportunity-list">
        {items.map((item) => (
          <article className="opportunity-card" key={item.id}>
            <div className="opportunity-score">
              <span>Impact</span>
              <strong>{impactScore(item)}</strong>
            </div>
            <div>
              <div className="opportunity-meta">
                <span className="priority-tag high">
                  {intentLabel(item.intent)}
                </span>
                <small>DataForSEO</small>
              </div>
              <h2>{item.keyword}</h2>
              <p className="opportunity-evidence">{evidence(item)}</p>
              <p>{item.recommended_action}</p>
              {item.target_url && (
                <small className="opportunity-target">
                  Bestaande pagina: {item.target_url}
                </small>
              )}
            </div>
            {item.target_url ? (
              <a
                className="icon-button"
                href={item.target_url}
                target="_blank"
                rel="noreferrer"
                aria-label={`Open ${item.target_url}`}
              >
                <ArrowUpRight size={18} />
              </a>
            ) : (
              <span />
            )}
          </article>
        ))}
      </div>
    </section>
  );
}

function impactScore(item: KeywordOpportunity) {
  const volumeScore = Math.min(70, Math.round((item.search_volume ?? 0) / 20));
  const difficultyBonus = Math.max(
    0,
    20 - Math.round((item.keyword_difficulty ?? 50) / 5),
  );
  const intentBonus = item.intent === "commercial" ? 10 : 5;
  return Math.min(100, volumeScore + difficultyBonus + intentBonus);
}

function evidence(item: KeywordOpportunity) {
  const parts = [
    `${(item.search_volume ?? 0).toLocaleString("nl-NL")} zoekopdrachten p/m`,
    item.keyword_difficulty === null
      ? null
      : `moeilijkheid ${item.keyword_difficulty}`,
    item.competition_level
      ? `concurrentie ${item.competition_level.toLowerCase()}`
      : null,
    item.cpc === null
      ? null
      : `CPC €${Number(item.cpc).toLocaleString("nl-NL", {
          minimumFractionDigits: 2,
          maximumFractionDigits: 2,
        })}`,
  ];
  return parts.filter(Boolean).join(" · ");
}

function intentLabel(intent: string | null) {
  const labels: Record<string, string> = {
    commercial: "Commercieel",
    transactional: "Transactie",
    informational: "Informatie",
    navigational: "Navigatie",
  };
  return intent ? (labels[intent] ?? intent) : "Zoekwoordkans";
}
