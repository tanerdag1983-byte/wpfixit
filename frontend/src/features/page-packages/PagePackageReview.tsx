import { CheckCircle2, FileEdit, LoaderCircle } from "lucide-react";
import { useEffect, useState } from "react";

import { apiRequest } from "../../lib/api";
import { ProposalRegenerationPanel } from "./ProposalRegenerationPanel";
import { ProposalVersionCompare } from "./ProposalVersionCompare";
import type {
  BlueprintSchema,
  DraftJob,
  PagePackage,
  Proposal,
  ProposalCandidate,
  ProposalHandoffIssueResponse,
} from "./proposalTypes";

export function PagePackageReview({ projectId }: { projectId: string }) {
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [candidate, setCandidate] = useState<ProposalCandidate | null>(null);
  const [draft, setDraft] = useState<PagePackage | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [importUrl, setImportUrl] = useState<string | null>(null);

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
        setCandidate(readActiveCandidate(result));
        if (result.package?.title) setDraft(result.package);
        if (result.active_candidate?.status === "failed") {
          const details = result.active_candidate.candidate_package as
            | { _generation_error?: unknown }
            | undefined;
          setMessage(
            typeof details?._generation_error === "string"
              ? details._generation_error
              : "Nieuwe versie genereren mislukt.",
          );
        }
        setImportUrl(null);
        setLoading(false);
        if (
          result.state === "generating"
          || result.active_candidate?.status === "generating"
          || result.draft_job?.state === "queued"
          || result.draft_job?.state === "claimed"
        ) {
          pollTimer = window.setTimeout(loadProposal, 1500);
        }
      } catch (error) {
        if (!active) return;
        setMessage(
          error instanceof Error ? error.message : "Voorstel laden mislukt.",
        );
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
      setCandidate(readActiveCandidate(result));
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
      setCandidate(readActiveCandidate(result));
      setDraft(result.package);
      setMessage(
        "Voorstel goedgekeurd. Het WordPress-concept kan nu worden aangemaakt.",
      );
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Goedkeuren mislukt.");
    } finally {
      setBusy(false);
    }
  }

  async function generateVersion(
    payload:
      | { mode: "full"; instruction: string | null }
      | { mode: "block"; target_block_id: string; instruction: string | null },
  ) {
    if (!proposal) return;
    setBusy(true);
    setMessage("");
    try {
      const result = await apiRequest<{
        base_version: Proposal;
        candidate: ProposalCandidate;
      }>(`/projects/${projectId}/page-proposals/${proposal.id}/regenerate`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setProposal(result.base_version);
      setDraft(result.base_version.package);
      setCandidate(result.candidate);
      setMessage("Er staat nu een nieuwe gegenereerde versie klaar om te vergelijken.");
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "Nieuwe versie genereren mislukt.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function acceptCandidate() {
    if (!candidate) return;
    setBusy(true);
    setMessage("");
    try {
      const result = await apiRequest<{
        current_version: Proposal;
        revoked_handoff_ids: string[];
      }>(`/projects/${projectId}/page-proposals/candidates/${candidate.id}/accept`, {
        method: "POST",
      });
      setProposal(result.current_version);
      setDraft(result.current_version.package);
      setCandidate(null);
      setMessage(
        result.revoked_handoff_ids.length > 0
          ? "Nieuwe versie opgeslagen. Eerdere handoffs zijn automatisch ingetrokken."
          : "Nieuwe versie opgeslagen als actuele voorstelversie.",
      );
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "Nieuwe versie accepteren mislukt.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function discardCandidate() {
    if (!candidate) return;
    setBusy(true);
    setMessage("");
    try {
      await apiRequest<{ candidate: ProposalCandidate }>(
        `/projects/${projectId}/page-proposals/candidates/${candidate.id}/discard`,
        { method: "POST" },
      );
      setCandidate(null);
      setMessage("De gegenereerde kandidaat is verworpen.");
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "Kandidaat verwerpen mislukt.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function createOutboundDraft() {
    if (!proposal) return;
    setBusy(true);
    setMessage("");
    try {
      const draftJob = await apiRequest<DraftJob>(
        `/projects/${projectId}/page-proposals/${proposal.id}/draft-job`,
        { method: "POST" },
      );
      setProposal({ ...proposal, state: "draft_in_progress", draft_job: draftJob });
      setMessage("De concepttaak wacht op WordPress.");
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "WordPress-concept starten mislukt.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function createManualImport() {
    if (!proposal) return;
    setBusy(true);
    setMessage("");
    try {
      const result = await apiRequest<ProposalHandoffIssueResponse>(
        `/projects/${projectId}/page-proposals/${proposal.id}/handoffs`,
        { method: "POST" },
      );
      setImportUrl(result.import_url);
      window.open(result.import_url, "_blank", "noopener,noreferrer");
      setMessage(
        "De WordPress-importpagina is geopend. Rond daar het concept aanmaken af.",
      );
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "WordPress-import starten mislukt.",
      );
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return (
      <section className="page-package-review">
        <a className="back-link" href="#opportunities">
          Terug naar kansen
        </a>
        <p className="settings-empty">Paginavoorstel laden...</p>
      </section>
    );
  }

  if (proposal?.state === "generating") {
    return (
      <section className="page-package-review">
        <a className="back-link" href="#opportunities">
          Terug naar kansen
        </a>
        <p className="eyebrow">Nieuw WordPress-concept</p>
        <h1>Paginapakket wordt gemaakt</h1>
        <div className="generation-notice">
          <LoaderCircle className="spin" size={18} />
          AI maakt het complete pakket. Dit bericht blijft staan totdat alles
          klaar is.
        </div>
      </section>
    );
  }

  if (!proposal || !draft) {
    return (
      <section className="page-package-review">
        <a className="back-link" href="#opportunities">
          Terug naar kansen
        </a>
        <h1>Nieuw paginaconcept beoordelen</h1>
        <p className="settings-message">{proposal?.job?.error_message || message}</p>
      </section>
    );
  }

  const editable = proposal.state === "proposed";
  return (
    <section className="page-package-review">
      <a className="back-link" href="#opportunities">
        Terug naar kansen
      </a>
      <div className="page-heading">
        <div>
          <p className="eyebrow">Nieuw WordPress-concept</p>
          <h1>Paginapakket beoordelen</h1>
          <p className="subtitle">
            Controleer eerst alle inhoud. Er wordt pas na je goedkeuring een concept
            in WordPress aangemaakt.
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
            <strong>
              {proposal.blueprint.name} · versie {proposal.blueprint.version}
            </strong>
          </div>
          <div>
            <span>Paginatype</span>
            <strong>{proposal.blueprint.page_type}</strong>
          </div>
          <div>
            <span>Builder en SEO</span>
            <strong>
              {proposal.blueprint.builder} · {proposal.blueprint.seo_plugin}
            </strong>
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

      {candidate ? (
        <ProposalVersionCompare
          busy={busy}
          candidate={candidate}
          current={proposal}
          onAccept={acceptCandidate}
          onDiscard={discardCandidate}
        />
      ) : (
        <>
          <section className="page-package-preview-shell">
            <div>
              <p className="eyebrow">Voorbeeld</p>
              <h2>Actuele versie</h2>
            </div>
            <div
              aria-label="Pagina-voorbeeld"
              className="proposal-preview page-package-preview full-width"
              dangerouslySetInnerHTML={{
                __html: sanitizeHtml(
                  proposal.rendered_html || `<p>${proposal.package.title}</p>`,
                ),
              }}
            />
          </section>

          <div className="page-package-layout">
            <div className="page-package-form">
              <PackageFields
                draft={draft}
                disabled={!editable}
                onChange={setDraft}
                schema={proposal.config_snapshot.content_schema}
              />
              <ProposalRegenerationPanel
                blocks={proposal.config_snapshot.content_schema?.blocks ?? []}
                busy={busy}
                onGenerateBlock={(targetBlockId, instruction) =>
                  void generateVersion({
                    mode: "block",
                    target_block_id: targetBlockId,
                    instruction: instruction || null,
                  })
                }
                onGenerateFull={(instruction) =>
                  void generateVersion({
                    mode: "full",
                    instruction: instruction || null,
                  })
                }
              />
            </div>

            <aside className="page-package-sidebar page-package-sidebar-inline">
              <ol className="publish-steps">
                <li className="complete">
                  <CheckCircle2 size={16} /> Pakket gegenereerd
                </li>
                <li className={proposal.state !== "proposed" ? "complete" : ""}>
                  <CheckCircle2 size={16} /> Handmatig goedgekeurd
                </li>
                <li className={proposal.state === "draft_created" ? "complete" : ""}>
                  <FileEdit size={16} /> WordPress-concept aangemaakt
                </li>
              </ol>
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
              <button
                className="primary-button page-package-draft-button"
                disabled={proposal.state !== "approved" || busy || !!proposal.draft_job}
                onClick={createOutboundDraft}
                type="button"
              >
                WordPress-concept aanmaken
              </button>
              {proposal.draft_job && (
                <p className={`settings-message draft-job-${proposal.draft_job.state}`}>
                  {draftJobLabel(proposal.draft_job)}
                </p>
              )}
              {(proposal.draft_job?.state === "failed"
                || proposal.draft_job?.state === "cancelled") && (
                <button
                  className="secondary-button"
                  disabled={busy}
                  onClick={createManualImport}
                  type="button"
                >
                  Handmatige import openen
                </button>
              )}
              {importUrl && (
                <a
                  className="secondary-button wordpress-edit-link"
                  href={importUrl}
                  rel="noreferrer"
                  target="_blank"
                >
                  Importpagina opnieuw openen
                </a>
              )}
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
        </>
      )}

      {message && <p className="settings-message">{message}</p>}
    </section>
  );
}

function readActiveCandidate(proposal: Proposal) {
  if (!proposal.active_candidate) return null;
  if (proposal.active_candidate.status === "discarded") return null;
  if (proposal.active_candidate.status === "accepted") return null;
  return proposal.active_candidate;
}

function draftJobLabel(job: DraftJob): string {
  if (job.state === "queued") return "Wachten op WordPress";
  if (job.state === "claimed") return "WordPress maakt het concept";
  if (job.state === "completed") return "WordPress-concept aangemaakt";
  if (job.state === "cancelled") return "Concepttaak geannuleerd";
  return job.error_message || "Concepttaak mislukt";
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
          <TextField
            label="Paginatitel"
            value={draft.title}
            disabled={disabled}
            onChange={(value) => field("title", value)}
          />
          <TextField
            label="Slug"
            value={draft.slug}
            disabled={disabled}
            onChange={(value) => field("slug", value)}
          />
          <TextField
            label="SEO-title"
            value={draft.seo_title}
            disabled={disabled}
            onChange={(value) => field("seo_title", value)}
          />
          <TextField
            label="Focuszoekwoord"
            value={draft.focus_keyword}
            disabled={disabled}
            onChange={(value) => field("focus_keyword", value)}
          />
          <TextField
            wide
            label="Meta description"
            value={draft.meta_description}
            disabled={disabled}
            onChange={(value) => field("meta_description", value)}
          />
        </div>
      </section>
      {schema?.blocks.map((block, index) => (
        <section className="package-section blueprint-review-block" key={block.id}>
          <div className="blueprint-review-block-heading">
            <span>{String(index + 1).padStart(2, "0")}</span>
            <div>
              <p className="eyebrow">{block.semantic_role}</p>
              <h2>{block.label}</h2>
            </div>
          </div>
          <div className="settings-field-grid">
            {block.fields.map((blueprintField) => {
              const replacement = draft.replacements.find(
                (item) => item.field_id === blueprintField.id,
              );
              const value = replacement?.value ?? "";
              const change = (nextValue: string) =>
                onChange({
                  ...draft,
                  replacements: replacement
                    ? draft.replacements.map((item) =>
                        item.field_id === blueprintField.id
                          ? { ...item, value: nextValue }
                          : item,
                      )
                    : [
                        ...draft.replacements,
                        { field_id: blueprintField.id, value: nextValue },
                      ],
                });
              if (blueprintField.value_type === "url") {
                const options = Array.from(
                  new Set(
                    ["", value, blueprintField.current_value].filter(
                      (option, optionIndex) => option || optionIndex === 0,
                    ),
                  ),
                );
                return (
                  <label key={blueprintField.id}>
                    {blueprintField.label}
                    <select
                      aria-label={blueprintField.label}
                      disabled={disabled}
                      value={value}
                      onChange={(event) => change(event.target.value)}
                    >
                      {options.map((option) => (
                        <option key={option || "empty"} value={option}>
                          {option || "Kies een goedgekeurde URL"}
                        </option>
                      ))}
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
        {draft.internal_links.map((link) => (
          <p key={`${link.anchor}:${link.url}`}>
            <strong>{link.anchor}</strong>
            <br />
            <small>{link.url}</small>
          </p>
        ))}
      </section>
    </>
  );
}

function TextField({
  label,
  value,
  disabled,
  multiline = false,
  wide = false,
  onChange,
}: {
  label: string;
  value: string;
  disabled: boolean;
  multiline?: boolean;
  wide?: boolean;
  onChange: (value: string) => void;
}) {
  return (
    <label className={wide ? "wide-field" : ""}>
      {label}
      {multiline ? (
        <textarea
          aria-label={label}
          disabled={disabled}
          value={value}
          onChange={(event) => onChange(event.target.value)}
        />
      ) : (
        <input
          aria-label={label}
          disabled={disabled}
          value={value}
          onChange={(event) => onChange(event.target.value)}
        />
      )}
    </label>
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

function stateLabel(state: Proposal["state"]) {
  return {
    generating: "Wordt gemaakt",
    proposed: "Te beoordelen",
    approved: "Goedgekeurd",
    draft_in_progress: "Concept wordt aangemaakt",
    draft_created: "Concept aangemaakt",
    failed: "Mislukt",
  }[state];
}
