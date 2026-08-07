import { RefreshCw } from "lucide-react";

import type { PageTimelineEvent } from "../../lib/api";

export function PageTimeline({
  checking,
  events,
  latestSyncAt,
  nextCheckAt,
  onCheck,
  status,
}: {
  checking: boolean;
  events: PageTimelineEvent[];
  latestSyncAt: string;
  nextCheckAt: string;
  onCheck: () => void;
  status: string;
}) {
  const orderedEvents = [...events].sort((left, right) =>
    right.created_at.localeCompare(left.created_at) || right.id.localeCompare(left.id)
  );
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
    </section>
  );
}

function dateLabel(value: string) {
  return new Intl.DateTimeFormat("nl-NL", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function eventLabel(type: string) {
  return {
    version_observed: "Nieuwe paginaversie gezien",
    score_created: "Score berekend",
    proposal_created: "Voorstel gemaakt",
    proposal_approved: "Voorstel goedgekeurd",
    draft_created: "WordPress-concept gemaakt",
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
