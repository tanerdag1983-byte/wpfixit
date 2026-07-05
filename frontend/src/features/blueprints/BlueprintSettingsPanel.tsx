import { useEffect, useRef, useState } from "react";

import { apiRequest } from "../../lib/api";
import {
  BlueprintOutline,
  type BlueprintSchema,
  type SemanticRole,
} from "./BlueprintOutline";

type BlueprintState = "capture_required" | "capturing" | "ready" | "stale" | "invalid";

type Blueprint = {
  id: string;
  name: string;
  page_type: string;
  source_wordpress_page_id: string;
  wordpress_blueprint_id: number;
  builder: string;
  seo_plugin: string;
  version: number;
  structure_hash: string;
  content_schema: BlueprintSchema;
  state: BlueprintState;
  is_default_for_page_type: boolean;
  supersedes_id: string | null;
};

type WordPressPage = {
  id: string;
  wordpress_object_id: number;
  title: string;
  url: string;
};
type LegacyCandidate = {
  source_wordpress_page_id: string;
  builder: string;
  seo_plugin: string;
  state: "capture_required";
};

const stateLabels: Record<BlueprintState, string> = {
  capture_required: "Vastlegging nodig",
  capturing: "Wordt vastgelegd",
  ready: "Klaar voor conceptpagina's",
  stale: "Nieuwe versie nodig",
  invalid: "Ongeldige structuur",
};

const pageTypes = [
  ["service", "Dienstpagina"],
  ["brand", "Merkpagina"],
  ["location", "Locatiepagina"],
  ["blog", "Blogartikel"],
  ["generic", "Algemene pagina"],
] as const;

export function BlueprintSettingsPanel({
  projectId,
  onAvailabilityChange,
}: {
  projectId: string;
  onAvailabilityChange?: (available: boolean | null) => void;
}) {
  const [blueprints, setBlueprints] = useState<Blueprint[]>([]);
  const [pages, setPages] = useState<WordPressPage[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [name, setName] = useState("");
  const [pageType, setPageType] = useState("service");
  const [sourcePageId, setSourcePageId] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [registryStatus, setRegistryStatus] = useState<"loading" | "loaded" | "error">("loading");
  const [legacyCandidates, setLegacyCandidates] = useState<LegacyCandidate[]>([]);
  const projectIdRef = useRef(projectId);
  projectIdRef.current = projectId;

  useEffect(() => {
    let active = true;
    setBlueprints([]);
    setPages([]);
    setSelectedId("");
    setName("");
    setPageType("service");
    setSourcePageId("");
    setBusy(false);
    setMessage("");
    setRegistryStatus("loading");
    setLegacyCandidates([]);
    onAvailabilityChange?.(null);

    apiRequest<{ items: Blueprint[]; legacy_candidates?: LegacyCandidate[] }>(`/projects/${projectId}/page-blueprints`)
      .then((registry) => {
        if (!active) return;
        const items = registry.items ?? [];
        setBlueprints(items);
        setLegacyCandidates(registry.legacy_candidates ?? []);
        setSelectedId(items[0]?.id ?? "");
        setRegistryStatus("loaded");
        onAvailabilityChange?.(items.length > 0);
      })
      .catch((error) => {
        if (!active) return;
        setRegistryStatus("error");
        setMessage(error instanceof Error ? error.message : "Blueprints laden mislukt.");
      });

    apiRequest<{ items: WordPressPage[] }>(`/projects/${projectId}/wordpress-pages`)
      .then((inventory) => {
        if (active) setPages(inventory.items ?? []);
      })
      .catch((error) => {
        if (!active) return;
        setMessage(error instanceof Error ? error.message : "WordPress-pagina's laden mislukt.");
      });
    return () => {
      active = false;
    };
  }, [onAvailabilityChange, projectId]);

  const selected = blueprints.find((blueprint) => blueprint.id === selectedId) ?? null;
  const selectedSource = pages.find(
    (page) => page.id === selected?.source_wordpress_page_id,
  );

  function replaceBlueprint(updated: Blueprint, requestProjectId = projectId) {
    if (projectIdRef.current !== requestProjectId) return;
    setBlueprints((current) => {
      const exists = current.some((item) => item.id === updated.id);
      const normalized = updated.is_default_for_page_type
        ? current.map((item) =>
            item.page_type === updated.page_type
              ? { ...item, is_default_for_page_type: false }
              : item,
          )
        : current;
      return exists
        ? normalized.map((item) => (item.id === updated.id ? updated : item))
        : [...normalized, updated];
    });
    setSelectedId(updated.id);
    onAvailabilityChange?.(true);
  }

  async function createBlueprint() {
    if (!name.trim() || !sourcePageId) return;
    const requestProjectId = projectId;
    setBusy(true);
    setMessage("");
    try {
      const created = await apiRequest<Blueprint>(`/projects/${projectId}/page-blueprints`, {
        method: "POST",
        body: JSON.stringify({
          name: name.trim(),
          page_type: pageType,
          source_wordpress_page_id: sourcePageId,
        }),
      });
      if (projectIdRef.current !== requestProjectId) return;
      replaceBlueprint(created, requestProjectId);
      setName("");
      setMessage("Blueprint is vastgelegd vanuit WordPress.");
    } catch (error) {
      if (projectIdRef.current === requestProjectId) {
        setMessage(error instanceof Error ? error.message : "Blueprint maken mislukt.");
      }
    } finally {
      if (projectIdRef.current === requestProjectId) setBusy(false);
    }
  }

  async function action(path: string, method = "POST") {
    if (!selected) return;
    const requestProjectId = projectId;
    const selectedBlueprintId = selected.id;
    setBusy(true);
    setMessage("");
    try {
      const updated = await apiRequest<Blueprint>(
        `/projects/${requestProjectId}/page-blueprints/${selectedBlueprintId}${path}`,
        { method },
      );
      replaceBlueprint(updated, requestProjectId);
    } catch (error) {
      if (projectIdRef.current !== requestProjectId) return;
      const errorMessage = error instanceof Error ? error.message : "Blueprint bijwerken mislukt.";
      try {
        const persisted = await apiRequest<Blueprint>(
          `/projects/${requestProjectId}/page-blueprints/${selectedBlueprintId}`,
        );
        replaceBlueprint(persisted, requestProjectId);
      } catch {
        // Keep the current snapshot when the recovery read is unavailable.
      }
      if (projectIdRef.current === requestProjectId) setMessage(errorMessage);
    } finally {
      if (projectIdRef.current === requestProjectId) setBusy(false);
    }
  }

  async function saveRoles(roles: Record<string, SemanticRole>) {
    if (!selected) return false;
    const requestProjectId = projectId;
    const selectedBlueprintId = selected.id;
    setBusy(true);
    try {
      const updated = await apiRequest<Blueprint>(
        `/projects/${requestProjectId}/page-blueprints/${selectedBlueprintId}`,
        { method: "PUT", body: JSON.stringify({ semantic_roles: roles }) },
      );
      if (projectIdRef.current !== requestProjectId) return false;
      replaceBlueprint(updated, requestProjectId);
      setMessage("Semantische rollen zijn opgeslagen.");
      return true;
    } catch (error) {
      if (projectIdRef.current === requestProjectId) {
        setMessage(error instanceof Error ? error.message : "Rollen opslaan mislukt.");
      }
      return false;
    } finally {
      if (projectIdRef.current === requestProjectId) setBusy(false);
    }
  }

  async function removeBlueprint() {
    if (!selected) return;
    const requestProjectId = projectId;
    const selectedBlueprintId = selected.id;
    setBusy(true);
    try {
      await apiRequest<void>(`/projects/${requestProjectId}/page-blueprints/${selectedBlueprintId}`, {
        method: "DELETE",
      });
      if (projectIdRef.current !== requestProjectId) return;
      const remaining = blueprints.filter((item) => item.id !== selectedBlueprintId);
      setBlueprints(remaining);
      setSelectedId(remaining[0]?.id ?? "");
      onAvailabilityChange?.(remaining.length > 0);
    } catch (error) {
      if (projectIdRef.current === requestProjectId) {
        setMessage(error instanceof Error ? error.message : "Blueprint verwijderen mislukt.");
      }
    } finally {
      if (projectIdRef.current === requestProjectId) setBusy(false);
    }
  }

  return (
    <section className="blueprint-settings">
      <p className="eyebrow">Managed page blueprints</p>
      <div className="blueprint-section-heading">
        <div>
          <h2>WordPress-paginastructuren</h2>
          <p className="settings-intro">
            Kies een bestaande pagina. WP FixPilot bewaart de volledige builderstructuur
            en stelt alleen goedgekeurde tekstvelden open voor AI.
          </p>
        </div>
      </div>

      <div className="blueprint-create-row">
        <label>
          Blueprintnaam
          <input value={name} onChange={(event) => setName(event.target.value)} />
        </label>
        <label>
          Paginatype
          <select value={pageType} onChange={(event) => setPageType(event.target.value)}>
            {pageTypes.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
        <label>
          Referentiepagina
          <select value={sourcePageId} onChange={(event) => setSourcePageId(event.target.value)}>
            <option value="">Kies een WordPress-pagina</option>
            {pages.map((page) => <option key={page.id} value={page.id}>{page.title || page.url}</option>)}
          </select>
        </label>
        <button
          className="primary-button"
          disabled={busy || !name.trim() || !sourcePageId}
          onClick={createBlueprint}
          type="button"
        >
          {busy ? "Vastleggen..." : "Blueprint maken"}
        </button>
      </div>

      {message && <p aria-live="polite" className="form-message" role="status">{message}</p>}

      {registryStatus === "loading" ? (
        <p className="blueprint-migration-note">Blueprintregister laden...</p>
      ) : registryStatus === "error" ? (
        <p className="blueprint-migration-note">Blueprintregister kon niet worden geladen.</p>
      ) : blueprints.length === 0 ? (
        <p className="blueprint-migration-note">
          {legacyCandidates.length > 0
            ? "Geldige oude paginapakketinstellingen gevonden. Kies de bijbehorende referentiepagina hierboven om veilig een managed blueprint vast te leggen. De oude instellingen blijven behouden."
            : "Nog geen managed blueprint. Het oude paginapakket blijft hieronder beschikbaar totdat de eerste blueprint klaarstaat."}
        </p>
      ) : (
        <div className="blueprint-workspace">
          <nav aria-label="Projectblueprints" className="blueprint-registry">
            {blueprints.map((blueprint) => (
              <button
                className={blueprint.id === selectedId ? "active" : ""}
                aria-pressed={blueprint.id === selectedId}
                key={blueprint.id}
                onClick={() => setSelectedId(blueprint.id)}
                type="button"
              >
                <span>{blueprint.name}</span>
                <small>{blueprint.page_type} · v{blueprint.version}</small>
                <b>{stateLabels[blueprint.state]}</b>
              </button>
            ))}
          </nav>

          {selected && (
            <div className="blueprint-inspector">
              <header>
                <div>
                  <span className={`blueprint-state ${selected.state}`}>{stateLabels[selected.state]}</span>
                  <h3>{selected.name}</h3>
                  <p>
                    {selected.builder} · {selected.seo_plugin} · WordPress #{selected.wordpress_blueprint_id}
                  </p>
                  <p>Bron: {selectedSource?.title || selectedSource?.url || selected.source_wordpress_page_id}</p>
                </div>
                <div className="blueprint-actions">
                  {!selected.is_default_for_page_type && selected.state === "ready" && (
                    <button disabled={busy} onClick={() => action("/set-default")} type="button">Als standaard</button>
                  )}
                  <button disabled={busy} onClick={() => action("/validate")} type="button">Valideren</button>
                  <button disabled={busy} onClick={() => action("/new-version")} type="button">Nieuwe versie</button>
                  <button className="danger-link" disabled={busy} onClick={removeBlueprint} type="button">Verwijderen</button>
                </div>
              </header>
              {selected.is_default_for_page_type && <p className="blueprint-default">Standaard voor {selected.page_type}</p>}
              <BlueprintOutline disabled={busy} schema={selected.content_schema} onSave={saveRoles} />
            </div>
          )}
        </div>
      )}
    </section>
  );
}
