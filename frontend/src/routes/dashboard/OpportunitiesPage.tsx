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
  target_classification: "existing_page" | "new_page" | "review";
  target_score: number;
  target_evidence: string[];
  recommended_action: string | null;
  source: string;
  proposal_summary?: {
    state: string;
    current_version_id: string;
  } | null;
};

type OpportunityResponse = {
  items: KeywordOpportunity[];
};
type Blueprint = {
  id: string;
  name: string;
  page_type: PageType;
  version: number;
  state: string;
  is_default_for_page_type: boolean;
};

type PageType = "service" | "brand" | "location" | "blog" | "generic";

const pageTypes: Array<[PageType, string]> = [
  ["service", "Dienstpagina"],
  ["brand", "Merkpagina"],
  ["location", "Locatiepagina"],
  ["blog", "Blogartikel"],
  ["generic", "Algemene pagina"],
];

export function OpportunitiesPage({ projectId }: { projectId: string }) {
  const [items, setItems] = useState<KeywordOpportunity[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [creatingProposalId, setCreatingProposalId] = useState<string | null>(
    null,
  );
  const [proposalErrors, setProposalErrors] = useState<Record<string, string>>({});
  const [proposalPageTypes, setProposalPageTypes] = useState<Record<string, PageType | "">>({});
  const [message, setMessage] = useState("");
  const [blueprints, setBlueprints] = useState<Blueprint[]>([]);

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

  useEffect(() => {
    let active = true;
    setBlueprints([]);
    setProposalPageTypes({});
    apiRequest<{ items: Blueprint[] }>(`/projects/${projectId}/page-blueprints`)
      .then((response) => {
        if (active) setBlueprints(response.items ?? []);
      })
      .catch((error) => {
        if (active) {
          setMessage(error instanceof Error ? error.message : "Blueprints laden mislukt.");
        }
      });
    return () => { active = false; };
  }, [projectId]);

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

  async function createPageProposal(item: KeywordOpportunity) {
    const pageType = proposalPageTypes[item.id];
    if (!pageType) return;
    await startPageProposal(item, pageType);
  }

  async function startPageProposal(
    item: KeywordOpportunity,
    pageType: PageType,
  ) {
    setCreatingProposalId(item.id);
    setProposalErrors((current) => ({ ...current, [item.id]: "" }));
    try {
      const response = await apiRequest<{ id: string }>(
        `/projects/${projectId}/keyword-opportunities/${item.id}/page-proposal`,
        { method: "POST", body: JSON.stringify({ page_type: pageType }) },
      );
      window.sessionStorage.setItem(`page-proposal-id:${projectId}`, response.id);
      window.location.hash = "page-proposal";
    } catch (error) {
      setProposalErrors((current) => ({
        ...current,
        [item.id]: error instanceof Error
          ? error.message
          : "Paginavoorstel maken mislukt.",
      }));
    } finally {
      setCreatingProposalId(null);
    }
  }

  async function regenerateProposal(item: KeywordOpportunity) {
    const proposalId = item.proposal_summary?.current_version_id;
    if (!proposalId) return;
    setCreatingProposalId(item.id);
    setProposalErrors((current) => ({ ...current, [item.id]: "" }));
    try {
      const proposal = await apiRequest<{
        blueprint: { page_type: PageType } | null;
      }>(`/projects/${projectId}/page-proposals/${proposalId}`);
      const pageType = proposal.blueprint?.page_type;
      if (!pageType) {
        throw new Error("Het paginatype van dit voorstel is onbekend.");
      }
      await startPageProposal(item, pageType);
    } catch (error) {
      setProposalErrors((current) => ({
        ...current,
        [item.id]:
          error instanceof Error
            ? error.message
            : "Opnieuw genereren mislukt.",
      }));
      setCreatingProposalId(null);
    }
  }

  function openProposal(proposalId: string) {
    window.sessionStorage.setItem(`page-proposal-id:${projectId}`, proposalId);
    window.location.hash = "page-proposal";
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
                <span className={`target-tag ${item.target_classification}`}>
                  {targetLabel(item.target_classification)}
                </span>
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
            {item.target_classification === "new_page" && item.proposal_summary ? (
              <div className="opportunity-create-action">
                <span className="priority-tag generated">Gegenereerd</span>
                <button
                  className="secondary-button opportunity-create-button"
                  onClick={() => openProposal(item.proposal_summary!.current_version_id)}
                  type="button"
                >
                  Voorstel bekijken
                </button>
                <button
                  className="text-button"
                  onClick={() => void regenerateProposal(item)}
                  type="button"
                >
                  {creatingProposalId === item.id
                    ? "Voorstel maken..."
                    : "Opnieuw genereren"}
                </button>
                {proposalErrors[item.id] && (
                  <p className="opportunity-create-error" role="alert">
                    {proposalErrors[item.id]}
                  </p>
                )}
              </div>
            ) : item.target_classification === "new_page" ? (
              <div className="opportunity-create-action">
                <label>
                  <span>Paginatype</span>
                  <select
                    aria-label={`Paginatype voor ${item.keyword}`}
                    value={proposalPageTypes[item.id] ?? ""}
                    onChange={(event) =>
                      setProposalPageTypes((current) => ({
                        ...current,
                        [item.id]: event.target.value as PageType | "",
                      }))
                    }
                  >
                    <option value="">Kies paginatype</option>
                    {pageTypes.map(([value, label]) => {
                      const blueprint = blueprints.find(
                        (item) => item.page_type === value && item.state === "ready" && item.is_default_for_page_type,
                      );
                      return (
                        <option disabled={!blueprint} key={value} value={value}>
                          {blueprint ? `${label} · ${blueprint.name} v${blueprint.version}` : `${label} · geen standaardblueprint`}
                        </option>
                      );
                    })}
                  </select>
                </label>
                {!blueprints.some(
                  (blueprint) => blueprint.state === "ready" && blueprint.is_default_for_page_type,
                ) && <a className="back-link" href="#settings">Standaardblueprint instellen</a>}
                <button
                  className="secondary-button opportunity-create-button"
                  disabled={creatingProposalId === item.id || !proposalPageTypes[item.id]}
                  onClick={() => createPageProposal(item)}
                  type="button"
                >
                  {creatingProposalId === item.id
                    ? "Voorstel maken..."
                    : "Pagina laten maken"}
                </button>
                {proposalErrors[item.id] && (
                  <p className="opportunity-create-error" role="alert">
                    {proposalErrors[item.id]}
                  </p>
                )}
              </div>
            ) : item.target_url ? (
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

function targetLabel(classification: KeywordOpportunity["target_classification"]) {
  return {
    existing_page: "Bestaande pagina verbeteren",
    new_page: "Nieuwe pagina aanbevolen",
    review: "Keuze controleren",
  }[classification];
}
