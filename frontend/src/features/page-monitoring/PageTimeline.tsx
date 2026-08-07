import { RefreshCw } from "lucide-react";

import type {
  PageRecommendation,
  PageTimelineEvent,
  StoredScoreSnapshot,
} from "../../lib/api";

export function PageTimeline({
  checking,
  events,
  latestSyncAt,
  nextCheckAt,
  onCheck,
  recommendations,
  scores,
  status,
  capturedVersionId,
}: {
  checking: boolean;
  events: PageTimelineEvent[];
  latestSyncAt: string | null;
  nextCheckAt: string | null;
  onCheck: () => void;
  recommendations: PageRecommendation[];
  scores: StoredScoreSnapshot[];
  status: string;
  capturedVersionId: string | null;
}) {
  const orderedEvents = [...events].sort((left, right) =>
    right.created_at.localeCompare(left.created_at) || right.id.localeCompare(left.id)
  );
  const orderedScores = [...scores].sort((left, right) =>
    right.created_at.localeCompare(left.created_at) || right.id.localeCompare(left.id)
  );
  const openRecommendations = deduplicatedOpenRecommendations(recommendations);
  return (
    <section aria-labelledby="page-timeline-heading" className="package-section">
      <div className="proposal-compare-heading">
        <div>
          <p className="eyebrow">Monitoring</p>
          <h2 id="page-timeline-heading">Paginatijdlijn</h2>
        </div>
        <button
          className="secondary-button"
          disabled={checking}
          onClick={onCheck}
          type="button"
        >
          <RefreshCw size={16} /> {checking ? "Controleren..." : "Nu controleren"}
        </button>
      </div>
      <div className="blueprint-review-summary">
        <div><span>Status</span><strong>{statusLabel(status)}</strong></div>
        <div><span>Laatste controle</span><strong>{dateLabel(latestSyncAt)}</strong></div>
        <div><span>Volgende controle</span><strong>{dateLabel(nextCheckAt)}</strong></div>
      </div>
      {orderedEvents.length ? (
        <ol className="change-history">
          {orderedEvents.map((event) => (
            <li key={event.id}>
              <strong>{eventLabel(event.event_type)}</strong>{" "}
              <span>{dateLabel(event.created_at)}</span>
            </li>
          ))}
        </ol>
      ) : (
        <p className="settings-empty">Nog geen tijdlijngebeurtenissen.</p>
      )}

      <h3>Scoreverloop</h3>
      {orderedScores.length ? (
        <div aria-label="Scoreverloop per versie" className="crawl-history" role="table">
          <div className="crawl-history-row header" role="row">
            <span role="columnheader">Datum</span>
            <span role="columnheader">Score</span>
            <span role="columnheader">Versie</span>
            <span role="columnheader">Context</span>
          </div>
          {orderedScores.map((score) => (
            <div className="crawl-history-row" key={score.id} role="row">
              <span role="cell">{dateLabel(score.created_at)}</span>
              <strong role="cell">{score.overall_score}</strong>
              <span role="cell">{score.page_version_id}</span>
              <span role="cell">
                {score.page_version_id === capturedVersionId
                  ? "Vastgelegde bron"
                  : "Waargenomen versie"}
              </span>
            </div>
          ))}
        </div>
      ) : (
        <p className="settings-empty">Nog geen scorehistorie.</p>
      )}

      <h3>Open suggesties</h3>
      {openRecommendations.length ? (
        <ul className="change-history">
          {openRecommendations.map((recommendation) => (
            <li key={recommendation.id}>{recommendation.suggested_action}</li>
          ))}
        </ul>
      ) : (
        <p className="settings-empty">Geen open suggesties.</p>
      )}
    </section>
  );
}

function dateLabel(value: string | null) {
  if (!value) return "Nog niet gecontroleerd";
  return new Intl.DateTimeFormat("nl-NL", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function eventLabel(type: string) {
  return {
    version_observed: "Nieuwe paginaversie gezien",
    score_created: "Score berekend",
    page_checked: "Pagina gecontroleerd",
    recommendation_created: "Aanbeveling gemaakt",
    proposal_version_created: "Voorstelversie gemaakt",
    proposal_approved: "Voorstel goedgekeurd",
    candidate_created: "Gegenereerde kandidaat gemaakt",
    candidate_accepted: "Gegenereerde kandidaat geaccepteerd",
    candidate_discarded: "Gegenereerde kandidaat verworpen",
    candidate_failed: "Kandidaat genereren mislukt",
    draft_requested: "WordPress-concept aangevraagd",
    draft_created: "WordPress-concept gemaakt",
    draft_failed: "WordPress-concept mislukt",
    draft_cancelled: "WordPress-concept geannuleerd",
    published: "Publicatie gezien",
  }[type] ?? type.replaceAll("_", " ");
}

function statusLabel(status: string) {
  return {
    monitoring: "Wordt gevolgd",
    improved: "Verbeterd",
    needs_attention: "Aandacht nodig",
    proposal_ready: "Voorstel gereed",
    draft_ready: "Concept gereed",
  }[status] ?? status;
}

function deduplicatedOpenRecommendations(
  recommendations: PageRecommendation[],
) {
  const seen = new Set<string>();
  return recommendations.filter((recommendation) => {
    if (recommendation.state !== "open") return false;
    const key = recommendation.suggested_action.trim().toLocaleLowerCase("nl-NL");
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}
