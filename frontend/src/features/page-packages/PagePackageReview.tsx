import { CheckCircle2, FileEdit, LoaderCircle } from "lucide-react";
import { useEffect, useState } from "react";

import { apiRequest } from "../../lib/api";

type Section = { heading: string; body_html: string };
type Faq = { question: string; answer_html: string };
type InternalLink = { anchor: string; url: string };
type PagePackage = {
  title: string;
  slug: string;
  seo_title: string;
  meta_description: string;
  focus_keyword: string;
  hero_title: string;
  introduction_html: string;
  sections: Section[];
  faq: Faq[];
  cta: {
    title: string;
    body_html: string;
    button_label: string;
    button_url: string;
  };
  internal_links: InternalLink[];
};

type Proposal = {
  id: string;
  state: "generating" | "proposed" | "approved" | "draft_created" | "failed";
  package: PagePackage;
  rendered_html: string;
  provider: string | null;
  model: string | null;
  wordpress_edit_url?: string | null;
  job: { state: string; progress: number; error_message?: string | null } | null;
};

export function PagePackageReview({ projectId }: { projectId: string }) {
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [draft, setDraft] = useState<PagePackage | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    const proposalId = window.sessionStorage.getItem(
      `page-proposal-id:${projectId}`,
    );
    if (!proposalId) {
      setMessage("Er is nog geen paginavoorstel voor dit project geselecteerd.");
      setLoading(false);
      return;
    }
    let active = true;
    setLoading(true);
    apiRequest<Proposal>(`/projects/${projectId}/page-proposals/${proposalId}`)
      .then((result) => {
        if (!active) return;
        setProposal(result);
        setDraft(result.package);
      })
      .catch((error) => {
        if (active) {
          setMessage(error instanceof Error ? error.message : "Voorstel laden mislukt.");
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [projectId]);

  async function save() {
    if (!proposal || !draft) return;
    setBusy(true);
    setMessage("");
    try {
      const result = await apiRequest<Proposal>(
        `/projects/${projectId}/page-proposals/${proposal.id}`,
        { method: "PUT", body: JSON.stringify({ package: draft }) },
      );
      setProposal(result);
      setDraft(result.package);
      setMessage("Het complete paginapakket is opgeslagen.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Opslaan mislukt.");
    } finally {
      setBusy(false);
    }
  }

  async function approve() {
    if (!proposal) return;
    setBusy(true);
    setMessage("");
    try {
      const result = await apiRequest<Proposal>(
        `/projects/${projectId}/page-proposals/${proposal.id}/approve`,
        { method: "POST" },
      );
      setProposal(result);
      setDraft(result.package);
      setMessage("Voorstel goedgekeurd. Het WordPress-concept kan nu worden aangemaakt.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Goedkeuren mislukt.");
    } finally {
      setBusy(false);
    }
  }

  async function createDraft() {
    if (!proposal) return;
    setBusy(true);
    setMessage("");
    try {
      const result = await apiRequest<Proposal>(
        `/projects/${projectId}/page-proposals/${proposal.id}/create-draft`,
        { method: "POST" },
      );
      setProposal(result);
      setDraft(result.package);
      setMessage("Het WordPress-concept is aangemaakt en nog niet gepubliceerd.");
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "WordPress-concept maken mislukt.",
      );
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return (
      <section className="page-package-review">
        <a className="back-link" href="#opportunities">Terug naar kansen</a>
        <p className="settings-empty">Paginavoorstel laden...</p>
      </section>
    );
  }

  if (!proposal || !draft) {
    return (
      <section className="page-package-review">
        <a className="back-link" href="#opportunities">Terug naar kansen</a>
        <h1>Nieuw paginaconcept beoordelen</h1>
        <p className="settings-message">{message}</p>
      </section>
    );
  }

  const editable = proposal.state === "proposed";
  return (
    <section className="page-package-review">
      <a className="back-link" href="#opportunities">Terug naar kansen</a>
      <div className="page-heading">
        <div>
          <p className="eyebrow">Nieuw WordPress-concept</p>
          <h1>Paginapakket beoordelen</h1>
          <p className="subtitle">
            Controleer eerst alle inhoud. Er wordt pas na je goedkeuring een concept in
            WordPress aangemaakt.
          </p>
        </div>
        <span className={`publish-state ${proposal.state}`}>
          {stateLabel(proposal.state)}
        </span>
      </div>

      {proposal.state === "generating" && (
        <div className="generation-notice">
          <LoaderCircle className="spin" size={18} />
          AI maakt het complete pakket. Dit bericht blijft staan totdat alles klaar is.
        </div>
      )}

      <div className="page-package-layout">
        <div className="page-package-form">
          <PackageFields draft={draft} disabled={!editable} onChange={setDraft} />
          <div className="settings-actions">
            <button
              className="secondary-button"
              disabled={!editable || busy}
              onClick={save}
              type="button"
            >
              Wijzigingen opslaan
            </button>
            <button
              className="primary-button"
              disabled={!editable || busy}
              onClick={approve}
              type="button"
            >
              Voorstel goedkeuren
            </button>
          </div>
          {message && <p className="settings-message">{message}</p>}
        </div>

        <aside className="page-package-sidebar">
          <p className="eyebrow">Voorbeeld</p>
          <div
            aria-label="Pagina-voorbeeld"
            className="proposal-preview page-package-preview"
            dangerouslySetInnerHTML={{ __html: sanitizeHtml(proposal.rendered_html) }}
          />
          <ol className="publish-steps">
            <li className="complete"><CheckCircle2 size={16} /> Pakket gegenereerd</li>
            <li className={proposal.state !== "proposed" ? "complete" : ""}>
              <CheckCircle2 size={16} /> Handmatig goedgekeurd
            </li>
            <li className={proposal.state === "draft_created" ? "complete" : ""}>
              <FileEdit size={16} /> WordPress-concept aangemaakt
            </li>
          </ol>
          <button
            className="primary-button page-package-draft-button"
            disabled={proposal.state !== "approved" || busy}
            onClick={createDraft}
            type="button"
          >
            WordPress-concept aanmaken
          </button>
          {proposal.wordpress_edit_url && (
            <a
              className="secondary-button wordpress-edit-link"
              href={proposal.wordpress_edit_url}
              rel="noreferrer"
              target="_blank"
            >
              Concept openen in WordPress
            </a>
          )}
          {proposal.provider && (
            <small className="provider-note">
              Gegenereerd met {proposal.provider} · {proposal.model}
            </small>
          )}
        </aside>
      </div>
    </section>
  );
}

function PackageFields({
  draft,
  disabled,
  onChange,
}: {
  draft: PagePackage;
  disabled: boolean;
  onChange: (draft: PagePackage) => void;
}) {
  const field = (key: keyof PagePackage, value: string) =>
    onChange({ ...draft, [key]: value });
  return (
    <>
      <section className="package-section">
        <p className="eyebrow">Basis en SEO</p>
        <div className="settings-field-grid">
          <TextField label="Paginatitel" value={draft.title} disabled={disabled} onChange={(value) => field("title", value)} />
          <TextField label="Slug" value={draft.slug} disabled={disabled} onChange={(value) => field("slug", value)} />
          <TextField label="SEO-title" value={draft.seo_title} disabled={disabled} onChange={(value) => field("seo_title", value)} />
          <TextField label="Focuszoekwoord" value={draft.focus_keyword} disabled={disabled} onChange={(value) => field("focus_keyword", value)} />
          <TextField wide label="Meta description" value={draft.meta_description} disabled={disabled} onChange={(value) => field("meta_description", value)} />
        </div>
      </section>
      <section className="package-section">
        <p className="eyebrow">Pagina-inhoud</p>
        <div className="settings-field-grid">
          <TextField wide label="Hero-titel" value={draft.hero_title} disabled={disabled} onChange={(value) => field("hero_title", value)} />
          <TextField wide multiline label="Introductie HTML" value={draft.introduction_html} disabled={disabled} onChange={(value) => field("introduction_html", value)} />
          {draft.sections.map((section, index) => (
            <div className="package-repeat wide-field" key={`section-${index}`}>
              <TextField label={`Sectie ${index + 1} titel`} value={section.heading} disabled={disabled} onChange={(value) => onChange({ ...draft, sections: draft.sections.map((item, itemIndex) => itemIndex === index ? { ...item, heading: value } : item) })} />
              <TextField multiline label={`Sectie ${index + 1} HTML`} value={section.body_html} disabled={disabled} onChange={(value) => onChange({ ...draft, sections: draft.sections.map((item, itemIndex) => itemIndex === index ? { ...item, body_html: value } : item) })} />
            </div>
          ))}
        </div>
      </section>
      <section className="package-section">
        <p className="eyebrow">FAQ</p>
        {draft.faq.map((item, index) => (
          <div className="package-repeat" key={`faq-${index}`}>
            <TextField label={`FAQ ${index + 1} vraag`} value={item.question} disabled={disabled} onChange={(value) => onChange({ ...draft, faq: draft.faq.map((faq, itemIndex) => itemIndex === index ? { ...faq, question: value } : faq) })} />
            <TextField multiline label={`FAQ ${index + 1} antwoord HTML`} value={item.answer_html} disabled={disabled} onChange={(value) => onChange({ ...draft, faq: draft.faq.map((faq, itemIndex) => itemIndex === index ? { ...faq, answer_html: value } : faq) })} />
          </div>
        ))}
      </section>
      <section className="package-section">
        <p className="eyebrow">CTA en interne links</p>
        <div className="settings-field-grid">
          <TextField label="CTA-titel" value={draft.cta.title} disabled={disabled} onChange={(value) => onChange({ ...draft, cta: { ...draft.cta, title: value } })} />
          <TextField label="CTA-knoptekst" value={draft.cta.button_label} disabled={disabled} onChange={(value) => onChange({ ...draft, cta: { ...draft.cta, button_label: value } })} />
          <TextField wide multiline label="CTA HTML" value={draft.cta.body_html} disabled={disabled} onChange={(value) => onChange({ ...draft, cta: { ...draft.cta, body_html: value } })} />
          <TextField wide label="CTA-link" value={draft.cta.button_url} disabled={disabled} onChange={(value) => onChange({ ...draft, cta: { ...draft.cta, button_url: value } })} />
          {draft.internal_links.map((link, index) => (
            <div className="package-repeat wide-field" key={`link-${index}`}>
              <TextField label={`Interne link ${index + 1} ankertekst`} value={link.anchor} disabled={disabled} onChange={(value) => onChange({ ...draft, internal_links: draft.internal_links.map((item, itemIndex) => itemIndex === index ? { ...item, anchor: value } : item) })} />
              <TextField label={`Interne link ${index + 1} URL`} value={link.url} disabled={disabled} onChange={(value) => onChange({ ...draft, internal_links: draft.internal_links.map((item, itemIndex) => itemIndex === index ? { ...item, url: value } : item) })} />
            </div>
          ))}
        </div>
      </section>
    </>
  );
}

function TextField({ label, value, disabled, multiline = false, wide = false, onChange }: { label: string; value: string; disabled: boolean; multiline?: boolean; wide?: boolean; onChange: (value: string) => void }) {
  return (
    <label className={wide ? "wide-field" : ""}>
      {label}
      {multiline ? (
        <textarea aria-label={label} disabled={disabled} value={value} onChange={(event) => onChange(event.target.value)} />
      ) : (
        <input aria-label={label} disabled={disabled} value={value} onChange={(event) => onChange(event.target.value)} />
      )}
    </label>
  );
}

function sanitizeHtml(value: string) {
  const template = document.createElement("template");
  template.innerHTML = value;
  template.content.querySelectorAll("script,style,iframe,object,embed,form").forEach((node) => node.remove());
  template.content.querySelectorAll("*").forEach((element) => {
    for (const attribute of Array.from(element.attributes)) {
      const name = attribute.name.toLowerCase();
      const safeHref = name === "href" && (/^https:\/\//i.test(attribute.value) || attribute.value.startsWith("/"));
      if (!safeHref) element.removeAttribute(attribute.name);
    }
  });
  return template.innerHTML;
}

function stateLabel(state: Proposal["state"]) {
  return { generating: "Wordt gemaakt", proposed: "Te beoordelen", approved: "Goedgekeurd", draft_created: "Concept aangemaakt", failed: "Mislukt" }[state];
}
