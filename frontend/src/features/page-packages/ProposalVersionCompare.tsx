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
            <strong>{current.package.title}</strong>
          </header>
          <div
            aria-label="Huidige versie"
            className="proposal-preview page-package-preview"
            dangerouslySetInnerHTML={{
              __html: sanitizeHtml(current.rendered_html || `<p>${current.package.title}</p>`),
            }}
          />
        </article>

        <article className="proposal-compare-column">
          <header>
            <span className="publish-state approved">Gegenereerd</span>
            <strong>{candidate.candidate_package?.title || current.package.title}</strong>
          </header>
          <div
            aria-label="Gegenereerde versie"
            className="proposal-preview page-package-preview"
            dangerouslySetInnerHTML={{
              __html: sanitizeHtml(
                candidate.candidate_rendered_html ||
                  `<p>${candidate.candidate_package?.title || current.package.title}</p>`,
              ),
            }}
          />
        </article>
      </div>
    </section>
  );
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
