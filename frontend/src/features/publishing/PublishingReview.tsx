import { AlertTriangle, CheckCircle2, RotateCcw, Upload } from "lucide-react";
import { useEffect, useState } from "react";

import { apiRequest } from "../../lib/api";

type ProposalState =
  | "proposed"
  | "approved"
  | "publishing"
  | "published"
  | "conflict"
  | "rolled_back";

type Proposal = {
  id: string;
  url: string;
  change_type: string;
  before_value: unknown;
  after_value: unknown;
  approval_state: ProposalState;
  created_at: string;
};

export function PublishingReview({ projectId }: { projectId: string }) {
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [afterValue, setAfterValue] = useState("");
  const [confirmRollback, setConfirmRollback] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    let active = true;
    apiRequest<{ items: Proposal[] }>(
      `/projects/${projectId}/change-proposals`,
    )
      .then((response) => {
        if (!active) return;
        const latest = response.items[0] ?? null;
        setProposal(latest);
        setAfterValue(stringValue(latest?.after_value));
      })
      .catch((error: unknown) => {
        if (active) {
          setMessage(
            error instanceof Error ? error.message : "Voorstel laden mislukt.",
          );
        }
      });
    return () => {
      active = false;
    };
  }, [projectId]);

  async function saveChange() {
    if (!proposal) return;
    try {
      const updated = await apiRequest<Proposal>(
        `/projects/${projectId}/change-proposals/${proposal.id}`,
        {
          method: "PUT",
          body: JSON.stringify({ after_value: afterValue }),
        },
      );
      setProposal(updated);
      setMessage("De voorgestelde waarde is opgeslagen.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Opslaan mislukt.");
    }
  }

  async function approve() {
    if (!proposal) return;
    try {
      const updated = await apiRequest<Proposal>(
        `/projects/${projectId}/change-proposals/${proposal.id}/approve`,
        { method: "POST" },
      );
      setProposal(updated);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Goedkeuren mislukt.");
    }
  }

  async function publish() {
    if (!proposal) return;
    try {
      const response = await apiRequest<{ proposal: Proposal }>(
        `/projects/${projectId}/change-proposals/${proposal.id}/publish`,
        { method: "POST" },
      );
      setProposal(response.proposal);
      setMessage("De wijziging is gepubliceerd.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Publiceren mislukt.");
    }
  }

  async function rollback() {
    if (!proposal) return;
    try {
      const response = await apiRequest<{ proposal: Proposal }>(
        `/projects/${projectId}/change-proposals/${proposal.id}/rollback`,
        {
          method: "POST",
          body: JSON.stringify({ confirmed: true }),
        },
      );
      setProposal(response.proposal);
      setConfirmRollback(false);
      setMessage("De wijziging is teruggedraaid.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Rollback mislukt.");
    }
  }

  if (!proposal) {
    return (
      <section className="publishing-review">
        <p className="eyebrow">Handmatige publicatie</p>
        <h1>Wijziging beoordelen</h1>
        <p className="settings-empty">Nog geen wijzigingsvoorstel beschikbaar.</p>
        {message && <p className="settings-message">{message}</p>}
      </section>
    );
  }

  const state = proposal.approval_state;
  return (
    <section className="publishing-review">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Handmatige publicatie</p>
          <h1>Wijziging beoordelen</h1>
          <p className="subtitle">
            {new URL(proposal.url).pathname} · {proposal.change_type}
          </p>
        </div>
        <span className={`publish-state ${state}`}>{stateLabel(state)}</span>
      </div>

      {state === "conflict" && (
        <div className="conflict-notice" role="alert">
          <AlertTriangle size={18} />
          WordPress is gewijzigd. Vernieuw het voorstel voordat je publiceert.
        </div>
      )}

      <div className="publishing-grid">
        <section>
          <div className="section-heading">
            <div>
              <p className="eyebrow">Exacte wijziging</p>
              <h2>Before / after</h2>
            </div>
          </div>
          <div className="diff-grid">
            <div className="diff-before">
              <span>Huidig</span>
              <p>{stringValue(proposal.before_value)}</p>
            </div>
            <label className="diff-after">
              <span>Voorstel</span>
              <textarea
                aria-label="Voorgestelde waarde"
                disabled={state !== "proposed"}
                value={afterValue}
                onChange={(event) => setAfterValue(event.target.value)}
              />
            </label>
          </div>
          <button
            className="secondary-button"
            disabled={state !== "proposed"}
            onClick={saveChange}
            type="button"
          >
            Wijziging opslaan
          </button>
          {message && <p className="settings-message">{message}</p>}
        </section>

        <aside className="publish-sidebar">
          <p className="eyebrow">Controle</p>
          <h2>Publicatiestappen</h2>
          <ol className="publish-steps">
            <li className="complete">
              <CheckCircle2 size={16} />
              Voorstel aangemaakt
            </li>
            <li className={state !== "proposed" ? "complete" : ""}>
              <CheckCircle2 size={16} />
              Handmatig goedgekeurd
            </li>
            <li className={state === "published" ? "complete" : ""}>
              <Upload size={16} />
              Naar WordPress gepubliceerd
            </li>
          </ol>
          <div className="publish-actions">
            <button
              className="secondary-button"
              disabled={state !== "proposed"}
              onClick={approve}
              type="button"
            >
              Goedkeuren
            </button>
            <button
              className="primary-button"
              disabled={state !== "approved"}
              onClick={publish}
              type="button"
            >
              Publiceren
            </button>
            {state === "published" && (
              <button
                className="rollback-button"
                onClick={() => setConfirmRollback(true)}
                type="button"
              >
                <RotateCcw size={15} />
                Rollback
              </button>
            )}
          </div>
        </aside>
      </div>

      {confirmRollback && (
        <div className="dialog-backdrop" role="presentation">
          <div className="dialog" role="dialog" aria-modal="true">
            <h2>Rollback bevestigen</h2>
            <p>De oude waarde wordt als gelogde wijziging teruggezet.</p>
            <div className="dialog-actions">
              <button
                className="secondary-button"
                onClick={() => setConfirmRollback(false)}
                type="button"
              >
                Annuleren
              </button>
              <button className="primary-button" onClick={rollback} type="button">
                Bevestig rollback
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

function stringValue(value: unknown) {
  if (value === null || value === undefined) return "";
  return typeof value === "string" ? value : JSON.stringify(value, null, 2);
}

function stateLabel(state: ProposalState) {
  return {
    proposed: "Voorstel",
    approved: "Goedgekeurd",
    publishing: "Publiceren",
    published: "Gepubliceerd",
    conflict: "Conflict",
    rolled_back: "Teruggedraaid",
  }[state];
}
