import type { Proposal, ProposalCandidate } from "./proposalTypes";

type ProposalVersionCompareProps = {
  busy: boolean;
  candidate: ProposalCandidate;
  current: Proposal;
  onAccept: () => void;
  onDiscard: () => void;
};

export function ProposalVersionCompare({
  busy,
  candidate,
  current,
  onAccept,
  onDiscard,
}: ProposalVersionCompareProps) {
  const currentTitle = proposalTitle(current);
  const candidateTitle = candidate.candidate_package
    ? packageTitle(candidate.candidate_package)
    : currentTitle;
  const snapshotChanges = candidate.candidate_package
    ? changedSnapshotFields(
        current,
        candidate.candidate_package,
      )
    : [];
  return (
    <section className="proposal-compare-shell">
      <div className="proposal-compare-heading">
        <div>
          <p className="eyebrow">Gegenereerd</p>
          <h2>Vergelijk gegenereerde versie</h2>
          <p className="settings-intro">
            Controleer eerst het verschil. Pas na jouw keuze wordt deze versie de
            nieuwe basis.
          </p>
        </div>
        <div className="proposal-compare-actions">
          <button
            className="secondary-button"
            disabled={busy}
            onClick={onDiscard}
            type="button"
          >
            Kandidaat verwerpen
          </button>
          <button
            className="primary-button"
            disabled={busy}
            onClick={onAccept}
            type="button"
          >
            Deze versie gebruiken
          </button>
        </div>
      </div>

      <div className="proposal-compare-grid">
        <article className="proposal-compare-column">
          <header>
            <span className="publish-state proposed">Huidige versie</span>
            <strong>{currentTitle}</strong>
          </header>
          {snapshotChanges.length > 0 ? (
            <SnapshotChanges changes={snapshotChanges} side="current" />
          ) : (
            <div
              aria-label="Huidige versie"
              className="proposal-preview page-package-preview"
              dangerouslySetInnerHTML={{
                __html: sanitizeHtml(current.rendered_html || `<p>${currentTitle}</p>`),
              }}
            />
          )}
        </article>

        <article className="proposal-compare-column">
          <header>
            <span className="publish-state approved">Gegenereerd</span>
            <strong>{candidateTitle}</strong>
          </header>
          {snapshotChanges.length > 0 ? (
            <SnapshotChanges changes={snapshotChanges} side="candidate" />
          ) : (
            <div
              aria-label="Gegenereerde versie"
              className="proposal-preview page-package-preview"
              dangerouslySetInnerHTML={{
                __html: sanitizeHtml(
                  candidate.candidate_rendered_html ||
                    `<p>${candidateTitle}</p>`,
                ),
              }}
            />
          )}
        </article>
      </div>
    </section>
  );
}

type SnapshotChange = {
  id: string;
  label: string;
  current: string;
  candidate: string;
};

function SnapshotChanges({
  changes,
  side,
}: {
  changes: SnapshotChange[];
  side: "current" | "candidate";
}) {
  return (
    <div
      aria-label={side === "current" ? "Huidige versie" : "Gegenereerde versie"}
      className="proposal-preview page-package-preview"
    >
      {changes.map((change) => (
        <div key={change.id}>
          <strong>{change.label}</strong>
          <p>{change[side] || "Leeg"}</p>
        </div>
      ))}
    </div>
  );
}

function changedSnapshotFields(
  current: Proposal,
  candidatePackage: Proposal["package"],
): SnapshotChange[] {
  if (
    !("text_replacements" in current.package)
    || !("text_replacements" in candidatePackage)
  ) {
    return [];
  }
  const currentReplacements = current.package.text_replacements;
  const candidateReplacements = candidatePackage.text_replacements;
  const labels = new Map(
    [
      ...(current.config_snapshot.content_schema?.document_fields ?? []),
      ...(current.config_snapshot.content_schema?.blocks.flatMap(
        (block) => block.fields,
      ) ?? []),
    ].map((field) => [field.id, field.label]),
  );
  return Array.from(
    new Set([
      ...Object.keys(currentReplacements),
      ...Object.keys(candidateReplacements),
    ]),
  )
    .filter(
      (fieldId) =>
        currentReplacements[fieldId] !== candidateReplacements[fieldId],
    )
    .map((fieldId) => ({
      id: fieldId,
      label: labels.get(fieldId) ?? fieldId,
      current: currentReplacements[fieldId] ?? "",
      candidate: candidateReplacements[fieldId] ?? "",
    }));
}

function proposalTitle(proposal: Proposal) {
  return packageTitle(proposal.package);
}

function packageTitle(packageValue: Proposal["package"]) {
  return "text_replacements" in packageValue
    ? packageValue.text_replacements["document:title"] || "Gegenereerde pagina"
    : packageValue.title;
}

function sanitizeHtml(value: string) {
  const template = document.createElement("template");
  template.innerHTML = value;
  template.content
    .querySelectorAll("script,style,iframe,object,embed,form")
    .forEach((node) => node.remove());
  template.content.querySelectorAll("*").forEach((element) => {
    for (const attribute of Array.from(element.attributes)) {
      const name = attribute.name.toLowerCase();
      const safeHref =
        name === "href" &&
        (/^https:\/\//i.test(attribute.value) || attribute.value.startsWith("/"));
      if (!safeHref) element.removeAttribute(attribute.name);
    }
  });
  return template.innerHTML;
}
