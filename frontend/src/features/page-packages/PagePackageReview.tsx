import { CheckCircle2, FileEdit, LoaderCircle } from "lucide-react";
import { useEffect, useState } from "react";

import { apiRequest } from "../../lib/api";
import type { PageMonitoring } from "../../lib/api";
import { PageTimeline } from "../page-monitoring/PageTimeline";
import { ScoreFactors } from "../page-monitoring/ScoreFactors";
import { ProposalRegenerationPanel } from "./ProposalRegenerationPanel";
import { ProposalStageList } from "./ProposalStageList";
import { ProposalVersionCompare } from "./ProposalVersionCompare";
import type {
  BlueprintSchema,
  DraftJob,
  PagePackage,
  Proposal,
  ProposalCandidate,
  ProposalHandoffIssueResponse,
  ProposalPackage,
  SnapshotTextPackage,
} from "./proposalTypes";

export function PagePackageReview({ projectId }: { projectId: string }) {
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [candidate, setCandidate] = useState<ProposalCandidate | null>(null);
  const [draft, setDraft] = useState<ProposalPackage | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [monitoring, setMonitoring] = useState<PageMonitoring | null>(null);
  const [monitoringError, setMonitoringError] = useState("");
  const [monitoringLoading, setMonitoringLoading] = useState(false);
  const [checking, setChecking] = useState(false);
  const [monitoringRevision, setMonitoringRevision] = useState(0);
  const [importUrl, setImportUrl] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const proposalSourcePageId = sourcePageId(proposal);

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
        if (isProposalPackage(result.package)) setDraft(result.package);
        if (result.active_candidate?.status === "failed") {
          setMessage("Nieuwe versie genereren mislukt.");
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
        setMessage(actionError(error, "Voorstel laden mislukt."));
        setLoading(false);
      }
    };
    void loadProposal();
    return () => {
      active = false;
      if (pollTimer) window.clearTimeout(pollTimer);
    };
  }, [projectId, refreshKey]);

  useEffect(() => {
    const pageId = proposalSourcePageId;
    const proposalId = proposal?.id;
    if (!pageId || !proposalId) {
      setMonitoring(null);
      setMonitoringError("");
      setMonitoringLoading(false);
      return;
    }
    let active = true;
    setMonitoring(null);
    setMonitoringError("");
    setMonitoringLoading(true);
    apiRequest<PageMonitoring>(
      `/projects/${projectId}/wordpress-pages/${pageId}/monitoring?proposal_id=${encodeURIComponent(proposalId)}`,
    )
      .then((result) => {
        if (active) {
          setMonitoring(result);
          setMonitoringLoading(false);
        }
      })
      .catch((error) => {
        if (active) {
          setMonitoringError(actionError(error, "Paginamonitoring laden mislukt."));
          setMonitoringLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [monitoringRevision, projectId, proposal?.id, proposal?.state, proposalSourcePageId]);

  function writeDraft(activeProposal: Proposal, packageDraft: ProposalPackage) {
    return apiRequest<Proposal>(
      `/projects/${projectId}/page-proposals/${activeProposal.id}`,
      {
        method: "PUT",
        body: JSON.stringify({
          package: isSnapshotTextPackage(packageDraft)
            ? snapshotWritePackage(packageDraft)
            : packageDraft,
        }),
      },
    );
  }

  async function save() {
    if (!proposal || !draft) return;
    setBusy(true);
    setMessage("");
    setMonitoring(null);
    setMonitoringError("");
    setMonitoringLoading(true);
    try {
      const result = await writeDraft(proposal, draft);
      setProposal(result);
      setCandidate(readActiveCandidate(result));
      setDraft(result.package);
      setMonitoringRevision((current) => current + 1);
      setMessage("Het complete paginapakket is opgeslagen.");
    } catch (error) {
      setMessage(actionError(error, "Opslaan mislukt."));
      setMonitoringError("Monitoring kon niet worden vernieuwd omdat opslaan mislukte.");
      setMonitoringLoading(false);
    } finally {
      setBusy(false);
    }
  }

  async function approve() {
    if (!proposal) return;
    setBusy(true);
    setMessage("");
    try {
      let activeProposal = proposal;
      if (
        draft
        && JSON.stringify(draft) !== JSON.stringify(proposal.package)
      ) {
        setMonitoring(null);
        setMonitoringError("");
        setMonitoringLoading(true);
        try {
          activeProposal = await writeDraft(proposal, draft);
        } catch {
          setMonitoringError(
            "Monitoring kon niet worden vernieuwd omdat opslaan mislukte.",
          );
          setMonitoringLoading(false);
          setMessage(
            "Wijzigingen opslaan mislukt. Het voorstel is niet goedgekeurd.",
          );
          return;
        }
        setProposal(activeProposal);
        setCandidate(readActiveCandidate(activeProposal));
        setDraft(activeProposal.package);
        setMonitoringRevision((current) => current + 1);
      }
      const result = await apiRequest<Proposal>(
        `/projects/${projectId}/page-proposals/${activeProposal.id}/approve`,
        { method: "POST" },
      );
      setProposal(result);
      setCandidate(readActiveCandidate(result));
      setDraft(result.package);
      setMessage(
        "Voorstel goedgekeurd. Het WordPress-concept kan nu worden aangemaakt.",
      );
    } catch (error) {
      setMessage(actionError(error, "Goedkeuren mislukt."));
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
      setCandidate(
        result.candidate.status === "ready" ? result.candidate : null,
      );
      setMessage(
        result.candidate.status === "ready"
          ? "Er staat nu een nieuwe gegenereerde versie klaar om te vergelijken."
          : "Nieuwe versie wordt gegenereerd.",
      );
    } catch (error) {
      setMessage(actionError(error, "Nieuwe versie genereren mislukt."));
    } finally {
      setBusy(false);
    }
  }

  async function retryStage(stageName: "text" | "validation") {
    if (!proposal) return;
    setBusy(true);
    setMessage("");
    try {
      let activeProposal = proposal;
      if (
        stageName === "validation"
        && draft
        && JSON.stringify(draft) !== JSON.stringify(proposal.package)
      ) {
        activeProposal = await writeDraft(proposal, draft);
        setProposal(activeProposal);
        setCandidate(readActiveCandidate(activeProposal));
        setDraft(activeProposal.package);
        if (
          activeProposal.stages?.some(
            (stage) => stage.name === "validation" && stage.state === "ready",
          )
        ) {
          setMessage("Wijzigingen opgeslagen en gevalideerd.");
          return;
        }
      }
      const result = await apiRequest<Proposal>(
        `/projects/${projectId}/page-proposals/${activeProposal.id}/stages/${stageName}/retry`,
        { method: "POST" },
      );
      setProposal(result);
      if (isProposalPackage(result.package)) setDraft(result.package);
      if (stageName === "text" && result.id !== activeProposal.id) {
        window.sessionStorage.setItem(`page-proposal-id:${projectId}`, result.id);
        setRefreshKey((current) => current + 1);
      }
      setMessage(
        stageName === "text"
          ? "Tekst wordt opnieuw gegenereerd."
          : "Validatie is opnieuw uitgevoerd.",
      );
    } catch (error) {
      setMessage(actionError(error, "Opnieuw uitvoeren mislukt."));
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
      setMessage(actionError(error, "Nieuwe versie accepteren mislukt."));
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
      setMessage(actionError(error, "Kandidaat verwerpen mislukt."));
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
      setProposal({
        ...proposal,
        state: draftJob.state === "completed" ? "draft_created" : "draft_in_progress",
        draft_job: draftJob,
      });
      setMessage(
        draftJob.state === "completed"
          ? "WordPress-concept gecontroleerd."
          : "De concepttaak wacht op WordPress.",
      );
    } catch (error) {
      setMessage(actionError(error, "WordPress-concept starten mislukt."));
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
      setMessage(actionError(error, "WordPress-import starten mislukt."));
    } finally {
      setBusy(false);
    }
  }

  async function runManualCheck() {
    const pageId = proposalSourcePageId;
    const proposalId = proposal?.id;
    if (!pageId || !proposalId) return;
    setChecking(true);
    setMonitoring(null);
    setMonitoringError("");
    setMonitoringLoading(true);
    try {
      await apiRequest(
        `/projects/${projectId}/wordpress-pages/${pageId}/checks`,
        { method: "POST" },
      );
      const result = await apiRequest<PageMonitoring>(
        `/projects/${projectId}/wordpress-pages/${pageId}/monitoring?proposal_id=${encodeURIComponent(proposalId)}`,
      );
      setMonitoring(result);
      setMessage("De pagina is gecontroleerd.");
    } catch (error) {
      setMonitoringError(actionError(error, "Pagina controleren mislukt."));
    } finally {
      setMonitoringLoading(false);
      setChecking(false);
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

  if (proposal?.state === "generating" && !draft) {
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
        <p className="settings-message">
          {message || "Het paginavoorstel kon niet worden geladen."}
        </p>
      </section>
    );
  }

  const fieldErrors = proposalFieldErrors(proposal);
  const existingPage = !!proposalSourcePageId;
  const editable = proposal.state === "needs_attention"
    || (
      proposal.state === "proposed"
      && (existingPage || !isSnapshotTextPackage(draft))
    );
  const comparisons = existingPage
    ? comparisonFields(proposal.config_snapshot.content_schema, draft)
    : [];
  return (
    <section className="page-package-review">
      <a className="back-link" href="#opportunities">
        Terug naar kansen
      </a>
      <div className="page-heading">
        <div>
          <p className="eyebrow">
            {existingPage ? "Bestaande pagina verbeteren" : "Nieuw WordPress-concept"}
          </p>
          <h1>{existingPage ? "Verbeteringsvoorstel beoordelen" : "Paginapakket beoordelen"}</h1>
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
      {proposal.stages && proposal.stages.length > 0 && (
        <ProposalStageList
          busy={busy}
          fieldErrors={fieldErrors}
          onEditField={(fieldId) => {
            document.getElementById(fieldInputId(fieldId))?.focus();
          }}
          onRetryText={() => void retryStage("text")}
          onRetryValidation={() => void retryStage("validation")}
          stages={proposal.stages}
        />
      )}

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
                  proposal.rendered_html || `<p>${packageTitle(proposal.package)}</p>`,
                ),
              }}
            />
          </section>

          {existingPage && (
            <section aria-labelledby="current-proposed-heading" className="proposal-compare-shell">
              <div>
                <p className="eyebrow">Vastgelegde bronversie</p>
                <h2 id="current-proposed-heading">Huidig en voorgesteld</h2>
              </div>
              {monitoring?.live_changed_since_capture && (
                <p
                  aria-label="Live pagina gewijzigd sinds vastlegging"
                  className="settings-message"
                  role="status"
                >
                  De live pagina is intussen gewijzigd. Deze vergelijking blijft
                  gekoppeld aan de vastgelegde bronversie van dit voorstel.
                </p>
              )}
              <div className="proposal-compare-grid">
                {comparisons.map((field) => (
                  <div className="proposal-compare-column" key={field.id}>
                    <h3>{field.label}</h3>
                    <div className="diff-grid">
                      <div className="diff-before">
                        <span>Vastgelegd</span>
                        <p>{field.current || "Leeg"}</p>
                      </div>
                      <div className="diff-after">
                        <span>Voorgesteld</span>
                        <p>{field.proposed || "Leeg"}</p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}

          {existingPage && monitoringLoading && (
            <p
              aria-label="Monitoring laden"
              className="settings-message"
              role="status"
            >
              Paginamonitoring laden...
            </p>
          )}

          {existingPage && monitoring?.captured_score && monitoring.projected_score && (
            <ScoreFactors
              current={monitoring.captured_score}
              projected={monitoring.projected_score}
            />
          )}

          {existingPage && monitoring && !monitoring.captured_version && (
            <p className="settings-message" role="alert">
              De vastgelegde bronversie is niet beschikbaar. Daarom wordt geen
              vergelijking of verwachte score getoond.
            </p>
          )}

          {existingPage && monitoring && (
            <PageTimeline
              capturedVersionId={monitoring.captured_version?.id ?? null}
              checking={checking}
              events={monitoring.events}
              latestSyncAt={monitoring.latest_sync_at}
              nextCheckAt={monitoring.next_check_at}
              onCheck={() => void runManualCheck()}
              recommendations={monitoring.recommendations}
              scores={monitoring.scores}
              status={monitoring.page.status}
            />
          )}
          {monitoringError && <p className="settings-message" role="alert">{monitoringError}</p>}

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
                <li className={
                  ["approved", "draft_in_progress", "draft_created"].includes(
                    proposal.state,
                  )
                    ? "complete"
                    : ""
                }>
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
                  disabled={
                    !["proposed", "needs_attention"].includes(proposal.state)
                    || fieldErrors.some((error) => error.required)
                    || busy
                  }
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
              {proposal.draft_job?.state === "completed" && (
                <button
                  className="secondary-button"
                  disabled={busy}
                  onClick={createOutboundDraft}
                  type="button"
                >
                  Conceptstatus opnieuw controleren
                </button>
              )}
              {(proposal.draft_job?.state === "failed"
                || proposal.draft_job?.state === "cancelled") && (
                <div className="settings-actions">
                  <button
                    className="primary-button"
                    disabled={busy}
                    onClick={createOutboundDraft}
                    type="button"
                  >
                    Opnieuw proberen
                  </button>
                  <button
                    className="secondary-button"
                    disabled={busy}
                    onClick={createManualImport}
                    type="button"
                  >
                    Handmatige import openen
                  </button>
                </div>
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

      {message && (
        <p
          aria-label={message}
          aria-live="polite"
          className="settings-message"
          role="status"
        >
          {message}
        </p>
      )}
    </section>
  );
}

function readActiveCandidate(proposal: Proposal) {
  if (!proposal.active_candidate) return null;
  return proposal.active_candidate.status === "ready"
    ? proposal.active_candidate
    : null;
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
  draft: ProposalPackage;
  disabled: boolean;
  onChange: (draft: ProposalPackage) => void;
  schema?: BlueprintSchema;
}) {
  if (isSnapshotTextPackage(draft)) {
    return (
      <SnapshotPackageFields
        disabled={disabled}
        draft={draft}
        onChange={onChange}
        schema={schema}
      />
    );
  }
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

function SnapshotPackageFields({
  disabled,
  draft,
  onChange,
  schema,
}: {
  disabled: boolean;
  draft: SnapshotTextPackage;
  onChange: (draft: ProposalPackage) => void;
  schema?: BlueprintSchema;
}) {
  const sections = [
    {
      id: "document",
      label: "Basis en SEO",
      fields: schema?.document_fields ?? [],
    },
    ...(schema?.blocks ?? []).map((block) => ({
      id: block.id,
      label: block.label,
      fields: block.fields,
    })),
  ];
  return (
    <>
      {sections.map((section, index) => (
        <section className="package-section blueprint-review-block" key={section.id}>
          <div className="blueprint-review-block-heading">
            <span>{String(index + 1).padStart(2, "0")}</span>
            <div><h2>{section.label}</h2></div>
          </div>
          <div className="settings-field-grid">
            {section.fields.map((field) => {
              const value = draft.text_replacements[field.id] ?? "";
              const change = (nextValue: string) => onChange({
                text_replacements: {
                  ...draft.text_replacements,
                  [field.id]: nextValue,
                },
              });
              if (field.value_type === "url") {
                const options = Array.from(
                  new Set(["", value, field.current_value]),
                );
                return (
                  <label key={field.id}>
                    {field.label}
                    <select
                      aria-label={field.label}
                      disabled={disabled}
                      id={fieldInputId(field.id)}
                      onChange={(event) => change(event.target.value)}
                      value={value}
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
                  id={fieldInputId(field.id)}
                  key={field.id}
                  label={field.label}
                  multiline={field.value_type === "rich_text"}
                  onChange={change}
                  value={value}
                  wide={field.value_type === "rich_text"}
                />
              );
            })}
          </div>
        </section>
      ))}
    </>
  );
}

function TextField({
  id,
  label,
  value,
  disabled,
  multiline = false,
  wide = false,
  onChange,
}: {
  id?: string;
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
          id={id}
          value={value}
          onChange={(event) => onChange(event.target.value)}
        />
      ) : (
        <input
          aria-label={label}
          disabled={disabled}
          id={id}
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
    needs_attention: "Aanpassing nodig",
    proposed: "Te beoordelen",
    approved: "Goedgekeurd",
    draft_in_progress: "Concept wordt aangemaakt",
    draft_created: "Concept aangemaakt",
    failed: "Mislukt",
  }[state];
}

function isSnapshotTextPackage(
  value: ProposalPackage,
): value is SnapshotTextPackage {
  return "text_replacements" in value;
}

function isProposalPackage(value: unknown): value is ProposalPackage {
  return !!value
    && typeof value === "object"
    && ("title" in value || "text_replacements" in value);
}

function snapshotWritePackage(draft: SnapshotTextPackage) {
  return {
    text_replacements: Object.fromEntries(
      Object.entries(draft.text_replacements).map(([fieldId, value]) => [
        fieldId,
        { value },
      ]),
    ),
  };
}

function packageTitle(value: ProposalPackage) {
  return isSnapshotTextPackage(value)
    ? value.text_replacements["document:title"] || "Gegenereerde pagina"
    : value.title;
}

function sourcePageId(proposal: Proposal | null) {
  return (proposal as (Proposal & { source_wordpress_page_id?: string | null }) | null)
    ?.source_wordpress_page_id ?? null;
}

function comparisonFields(schema: BlueprintSchema | undefined, draft: ProposalPackage) {
  const fields = [
    ...(schema?.document_fields ?? []),
    ...(schema?.blocks.flatMap((block) => block.fields) ?? []),
  ];
  return fields
    .map((field) => {
      const proposed = isSnapshotTextPackage(draft)
        ? draft.text_replacements[field.id] ?? ""
        : draft.replacements.find((item) => item.field_id === field.id)?.value ?? "";
      return {
        id: field.id,
        label: field.label,
        current: field.current_value,
        proposed,
      };
    })
    .filter((field) => field.current !== field.proposed);
}

function fieldInputId(fieldId: string) {
  return `proposal-field-${fieldId}`;
}

function proposalFieldErrors(proposal: Proposal) {
  const schema = proposal.config_snapshot.content_schema;
  const fields = new Map(
    [
      ...(schema?.document_fields ?? []),
      ...(schema?.blocks.flatMap((block) => block.fields) ?? []),
    ].map((field) => [field.id, field]),
  );
  return Object.entries(proposal.field_errors ?? {}).map(([fieldId, code]) => ({
    fieldId,
    label: fields.get(fieldId)?.label ?? "Veld",
    message: fieldErrorMessage(code),
    required: fields.get(fieldId)?.required ?? true,
  }));
}

function fieldErrorMessage(code: string) {
  return {
    unsafe_html: "bevat niet-toegestane opmaak",
    unapproved_url: "bevat een niet-goedgekeurde link",
    invalid_slug: "heeft geen geldige slug",
    max_length: "is te lang",
    required: "is verplicht",
    invalid_value: "heeft een ongeldige waarde",
  }[code] ?? "heeft een ongeldige waarde";
}

function actionError(error: unknown, fallback: string) {
  if (!(error instanceof Error)) return fallback;
  const message = error.message.trim();
  return {
    "Authentication required": "Je sessie is verlopen. Log opnieuw in.",
    "Blueprint changed; generate a new proposal":
      "De blueprint is gewijzigd. Genereer een nieuw voorstel.",
    "AI changed the focus keyword":
      "De AI wijzigde het focuszoekwoord. Genereer een nieuw voorstel.",
  }[message] ?? fallback;
}
