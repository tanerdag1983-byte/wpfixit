import { AlertTriangle, CheckCircle2, RotateCcw, Upload } from "lucide-react";
import { useState } from "react";

type ProposalState =
  | "proposed"
  | "approved"
  | "publishing"
  | "published"
  | "conflict"
  | "rolled_back";

export function PublishingReview({
  initialState = "proposed",
}: {
  initialState?: ProposalState;
}) {
  const [state, setState] = useState<ProposalState>(initialState);
  const [confirmRollback, setConfirmRollback] = useState(false);

  return (
    <section className="publishing-review">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Handmatige publicatie</p>
          <h1>Wijziging beoordelen</h1>
          <p className="subtitle">
            /revisie · SEO-title · gebaseerd op Search Console en WordPress
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
              <p>Oude title</p>
            </div>
            <div className="diff-after">
              <span>Voorstel</span>
              <p>Nieuwe title</p>
            </div>
          </div>
          <div className="publish-evidence">
            <strong>Waarom deze wijziging?</strong>
            <p>
              12.400 impressies, 1,2% CTR en positie 4,6. De huidige title
              benut de commerciële zoekintentie onvoldoende.
            </p>
            <small>Evidence: gsc:revisie · audit:82 · confidence 92%</small>
          </div>
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
              onClick={() => setState("approved")}
              type="button"
            >
              Goedkeuren
            </button>
            <button
              className="primary-button"
              disabled={state !== "approved"}
              onClick={() => setState("published")}
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

      <section className="change-history">
        <p className="eyebrow">Auditlog</p>
        <h2>Wijzigingshistorie</h2>
        <div>
          <span>Vandaag, 10:32</span>
          <strong>Voorstel aangemaakt</strong>
          <span>door Taner</span>
        </div>
        {state === "published" && (
          <div>
            <span>Vandaag, 10:36</span>
            <strong>Gepubliceerd naar WordPress</strong>
            <span>hash gecontroleerd</span>
          </div>
        )}
      </section>

      {confirmRollback && (
        <div className="dialog-backdrop" role="presentation">
          <div className="dialog" role="dialog" aria-modal="true">
            <h2>Rollback bevestigen</h2>
            <p>
              De oude title wordt als nieuwe, gelogde wijziging teruggezet.
            </p>
            <div className="dialog-actions">
              <button
                className="secondary-button"
                onClick={() => setConfirmRollback(false)}
                type="button"
              >
                Annuleren
              </button>
              <button
                className="primary-button"
                onClick={() => {
                  setState("rolled_back");
                  setConfirmRollback(false);
                }}
                type="button"
              >
                Bevestig rollback
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
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
