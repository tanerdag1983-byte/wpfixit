import type { ProposalStage } from "./proposalTypes";

type FieldError = {
  fieldId: string;
  label: string;
  message: string;
};

const stageLabels: Record<ProposalStage["name"], string> = {
  template: "Template gereed",
  text: "Tekst gereed",
  validation: "Gevalideerd",
};

const stateLabels: Record<ProposalStage["state"], string> = {
  pending: "Wacht",
  running: "Bezig",
  ready: "Klaar",
  attention: "Actie nodig",
  failed: "Mislukt",
};

export function ProposalStageList({
  busy,
  fieldErrors,
  onEditField,
  onRetryText,
  onRetryValidation,
  stages,
}: {
  busy: boolean;
  fieldErrors: FieldError[];
  onEditField: (fieldId: string) => void;
  onRetryText: () => void;
  onRetryValidation: () => void;
  stages: ProposalStage[];
}) {
  return (
    <section className="proposal-stage-panel" aria-label="Generatiestatus">
      <ol className="proposal-stage-list">
        {stages.map((stage) => (
          <li className={`proposal-stage ${stage.state}`} key={stage.name}>
            <div>
              <strong>{stageLabels[stage.name]}</strong>
              <span>{stateLabels[stage.state]}</span>
            </div>
            {stage.name === "text" && ["attention", "failed"].includes(stage.state) && (
              <button disabled={busy} onClick={onRetryText} type="button">
                Tekst opnieuw genereren
              </button>
            )}
            {stage.name === "validation"
              && ["attention", "failed"].includes(stage.state) && (
              <button disabled={busy} onClick={onRetryValidation} type="button">
                Validatie opnieuw uitvoeren
              </button>
            )}
          </li>
        ))}
        {fieldErrors.map((error) => (
          <li className="proposal-field-error" key={error.fieldId}>
            <span>{error.label} {error.message}</span>
            <button
              disabled={busy}
              onClick={() => onEditField(error.fieldId)}
              type="button"
            >
              Waarde aanpassen
            </button>
          </li>
        ))}
      </ol>
    </section>
  );
}
