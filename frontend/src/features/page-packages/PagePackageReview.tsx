import { CheckCircle2, FileEdit, LoaderCircle } from "lucide-react";
import { useEffect, useState } from "react";

import { apiRequest } from "../../lib/api";

type InternalLink = { anchor: string; url: string };
type Replacement = { field_id: string; value: string };
type PagePackage = {
  title: string;
  slug: string;
  seo_title: string;
  meta_description: string;
  focus_keyword: string;
  replacements: Replacement[];
  internal_links: InternalLink[];
};

type BlueprintField = {
  id: string;
  path: string;
  label: string;
  value_type: "plain_text" | "rich_text" | "heading" | "button_text" | "url";
  current_value: string;
  required: boolean;
  max_length: number;
};
type BlueprintSchema = {
  schema_version: "blueprint-v1";
  blocks: Array<{
    id: string;
    layout: string;
    label: string;
    semantic_role: string;
    fields: BlueprintField[];
  }>;
};

type Proposal = {
  id: string;
  state: "generating" | "proposed" | "approved" | "draft_created" | "failed";
  package: PagePackage;
  rendered_html: string;
  blueprint: {
    name: string;
    page_type: string;
    version: number;
    builder: string;
    seo_plugin: string;
    source_wordpress_page_id?: string;
  } | null;
  config_snapshot: { content_schema?: BlueprintSchema };
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
    let pollTimer: number | undefined;
    setLoading(true);
    const loadProposal = async () => {
      try {
        const result = await apiRequest<Proposal>(
          `/projects/${projectId}/page-proposals/${proposalId}`,
        );
        if (!active) return;
        setProposal(result);
        if (result.package?.title) setDraft(result.package);
        setLoading(false);
        if (result.state === "generating") {
          pollTimer = window.setTimeout(loadProposal, 1500);
        }
      } catch (error) {
        if (!active) return;
        setMessage(error instanceof Error ? error.message : "Voorstel laden mislukt.");
        setLoading(false);
      }
    };
    void loadProposal();
    return () => {
      active = false;
      if (pollTimer) window.clearTimeout(pollTimer);
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

  if (proposal?.state === "generating") {
    return (
      <section className="page-package-review">
        <a className="back-link" href="#opportunities">Terug naar kansen</a>
        <p className="eyebrow">Nieuw WordPress-concept</p>
        <h1>Paginapakket wordt gemaakt</h1>
        <div className="generation-notice">
          <LoaderCircle className="spin" size={18} />
          AI maakt het complete pakket. Dit bericht blijft staan totdat alles klaar is.
        </div>
      </section>
    );
  }

  if (!proposal || !draft) {
    return (
      <section className="page-package-review">
        <a className="back-link" href="#opportunities">Terug naar kansen</a>
        <h1>Nieuw paginaconcept beoordelen</h1>
        <p className="settings-message">
          {proposal?.job?.error_message || message}
        </p>
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

      {proposal.blueprint && (
        <div className="blueprint-review-summary">
          <div>
            <span>Gekozen blueprint</span>
            <strong>{proposal.blueprint.name} · versie {proposal.blueprint.version}</strong>
          </div>
          <div>
            <span>Paginatype</span>
            <strong>{proposal.blueprint.page_type}</strong>
          </div>
          <div>
            <span>Builder en SEO</span>
            <strong>{proposal.blueprint.builder} · {proposal.blueprint.seo_plugin}</strong>
          </div>
          <div>
            <span>Bronpagina</span>
            <strong>{proposal.blueprint.source_wordpress_page_id || "Onbekend"}</strong>
          </div>
        </div>
      )}
      <p className="blueprint-preserved-note">
        Afbeeldingen en vormgeving blijven uit de blueprint behouden.
      </p>

      <div className="page-package-layout">
        <div className="page-package-form">
          <PackageFields
            draft={draft}
            disabled={!editable}
            onChange={setDraft}
            schema={proposal.config_snapshot.content_schema}
          />
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
          <p className="eyebrow">Inhoudsoverzicht</p>
          <BlueprintPreview draft={draft} schema={proposal.config_snapshot.content_schema} />
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
  schema,
}: {
  draft: PagePackage;
  disabled: boolean;
  onChange: (draft: PagePackage) => void;
  schema?: BlueprintSchema;
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
      {schema?.blocks.map((block, index) => (
        <section className="package-section blueprint-review-block" key={block.id}>
          <div className="blueprint-review-block-heading">
            <span>{String(index + 1).padStart(2, "0")}</span>
            <div><p className="eyebrow">{block.semantic_role}</p><h2>{block.label}</h2></div>
          </div>
          <div className="settings-field-grid">
            {block.fields.map((blueprintField) => {
              const replacement = draft.replacements.find((item) => item.field_id === blueprintField.id);
              const value = replacement?.value ?? "";
              const change = (nextValue: string) => onChange({
                ...draft,
                replacements: replacement
                  ? draft.replacements.map((item) =>
                      item.field_id === blueprintField.id ? { ...item, value: nextValue } : item,
                    )
                  : [...draft.replacements, { field_id: blueprintField.id, value: nextValue }],
              });
              if (blueprintField.value_type === "url") {
                const options = Array.from(new Set(["", value, blueprintField.current_value].filter((option, optionIndex) => option || optionIndex === 0)));
                return (
                  <label key={blueprintField.id}>
                    {blueprintField.label}
                    <select aria-label={blueprintField.label} disabled={disabled} value={value} onChange={(event) => change(event.target.value)}>
                      {options.map((option) => <option key={option || "empty"} value={option}>{option || "Kies een goedgekeurde URL"}</option>)}
                    </select>
                  </label>
                );
              }
              return (
                <TextField
                  disabled={disabled}
                  key={blueprintField.id}
                  label={blueprintField.label}
                  multiline={blueprintField.value_type === "rich_text"}
                  onChange={change}
                  value={value}
                  wide={blueprintField.value_type === "rich_text"}
                />
              );
            })}
          </div>
        </section>
      ))}
      <section className="package-section">
        <p className="eyebrow">Goedgekeurde interne links</p>
        {draft.internal_links.map((link) => <p key={`${link.anchor}:${link.url}`}><strong>{link.anchor}</strong><br /><small>{link.url}</small></p>)}
      </section>
    </>
  );
}

function BlueprintPreview({ draft, schema }: { draft: PagePackage; schema?: BlueprintSchema }) {
  return (
    <div aria-label="Pagina-voorbeeld" className="proposal-preview page-package-preview">
      {schema?.blocks.map((block) => (
        <section key={block.id}>
          <strong>{block.label}</strong>
          {block.fields.map((field) => {
            const value = draft.replacements.find((item) => item.field_id === field.id)?.value ?? "";
            return field.value_type === "rich_text" ? (
              <div key={field.id} dangerouslySetInnerHTML={{ __html: sanitizeHtml(value) }} />
            ) : <p key={field.id}>{value}</p>;
          })}
        </section>
      ))}
    </div>
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
