import { useEffect, useState } from "react";

import { apiRequest } from "../../lib/api";

type Settings = {
  configured: boolean;
  builder?: string;
  template_wordpress_page_id?: string;
  seo_plugin?: string;
  slot_mapping?: Record<string, string>;
  validation_state: string;
};

type WordPressPage = {
  id: string;
  wordpress_object_id: number;
  title: string;
  url: string;
};

type TemplateSlot = {
  path: string;
  label: string;
  preview?: string;
  value_type: string;
};

const semanticSlots = [
  ["hero_title", "Hero-titel"],
  ["introduction", "Introductie"],
  ["main_content", "Hoofdinhoud"],
  ["faq", "FAQ"],
  ["cta_title", "CTA-titel (optioneel)"],
  ["cta_text", "CTA-tekst (optioneel)"],
] as const;

const requiredSemanticSlots = semanticSlots.filter(
  ([key]) => key !== "cta_title" && key !== "cta_text",
);

export function PagePackageSettingsPanel({ projectId }: { projectId: string }) {
  const [builder, setBuilder] = useState("gutenberg");
  const [templateId, setTemplateId] = useState("");
  const [seoPlugin, setSeoPlugin] = useState("yoast");
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [pages, setPages] = useState<WordPressPage[]>([]);
  const [detectedBuilders, setDetectedBuilders] = useState<string[]>([]);
  const [slots, setSlots] = useState<TemplateSlot[]>([]);
  const [configured, setConfigured] = useState(false);
  const [validationState, setValidationState] = useState("unconfigured");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    let active = true;
    Promise.all([
      apiRequest<Settings>(`/projects/${projectId}/page-package-settings`),
      apiRequest<{ items: WordPressPage[] }>(`/projects/${projectId}/wordpress-pages`),
      apiRequest<{ builders: string[]; seo_plugin: string | null }>(
        `/projects/${projectId}/page-package-settings/options`,
      ),
    ])
      .then(([settings, inventory, options]) => {
        if (!active) return;
        setPages(inventory.items ?? []);
        setDetectedBuilders(options.builders ?? []);
        setConfigured(Boolean(settings.configured));
        setValidationState(settings.validation_state ?? "unconfigured");
        if (settings.configured) {
          setBuilder(settings.builder ?? "gutenberg");
          setTemplateId(settings.template_wordpress_page_id ?? "");
          setSeoPlugin(settings.seo_plugin ?? "yoast");
          setMapping(settings.slot_mapping ?? {});
        } else {
          setBuilder(options.builders?.[0] ?? "gutenberg");
          setSeoPlugin(options.seo_plugin ?? "yoast");
        }
      })
      .catch((error) => {
        if (active) {
          setMessage(error instanceof Error ? error.message : "Paginapakket laden mislukt.");
        }
      });
    return () => {
      active = false;
    };
  }, [projectId]);

  async function persistSettings() {
    return apiRequest<Settings>(`/projects/${projectId}/page-package-settings`, {
      method: "PUT",
      body: JSON.stringify({
        builder,
        template_wordpress_page_id: templateId,
        seo_plugin: seoPlugin,
        slot_mapping: mapping,
      }),
    });
  }

  async function save() {
    setBusy(true);
    setMessage("");
    try {
      const settings = await persistSettings();
      setConfigured(true);
      setValidationState(settings.validation_state);
      setMessage("Paginapakket is opgeslagen en moet worden gevalideerd.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Paginapakket opslaan mislukt.");
    } finally {
      setBusy(false);
    }
  }

  async function inspectTemplate() {
    setBusy(true);
    setMessage("");
    try {
      const inspection = await apiRequest<{ slots: TemplateSlot[] }>(
        `/projects/${projectId}/page-package-settings/inspect-template`,
        { method: "POST" },
      );
      setSlots(inspection.slots);
      setMessage(`${inspection.slots.length} echte templateblokken gevonden.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Template inspecteren mislukt.");
    } finally {
      setBusy(false);
    }
  }

  async function validate() {
    setBusy(true);
    setMessage("");
    try {
      await persistSettings();
      const settings = await apiRequest<Settings>(
        `/projects/${projectId}/page-package-settings/validate`,
        { method: "POST" },
      );
      setValidationState(settings.validation_state);
      setMessage("Paginapakket is gevalideerd en klaar voor nieuwe conceptpagina's.");
    } catch (error) {
      setValidationState("invalid");
      setMessage(error instanceof Error ? error.message : "Paginapakket valideren mislukt.");
    } finally {
      setBusy(false);
    }
  }

  const mappedRequiredPaths = requiredSemanticSlots
    .map(([key]) => mapping[key])
    .filter(Boolean);
  const mappedPaths = semanticSlots.map(([key]) => mapping[key]).filter(Boolean);
  const duplicatePaths = new Set(
    mappedPaths.filter(
      (path, index) => mappedPaths.indexOf(path) !== index,
    ),
  );
  const duplicatePathsAreSafe =
    duplicatePaths.size === 0 ||
    (builder === "acf" && [...duplicatePaths].every((path) => path.startsWith("acf-block:")));
  const completeMapping =
    mappedRequiredPaths.length === requiredSemanticSlots.length && duplicatePathsAreSafe;

  return (
    <section>
      <p className="eyebrow">Nieuwe WordPress-pagina&apos;s</p>
      <h2>Standaard paginapakket</h2>
      <p className="settings-intro">
        Kies per project de builder, templatepagina en blokken die voor ieder nieuw
        AI-concept worden gebruikt.
      </p>
      <div className="settings-field-grid">
        <label>
          Page builder
          <select value={builder} onChange={(event) => setBuilder(event.target.value)}>
            {(detectedBuilders.length
              ? detectedBuilders
              : ["gutenberg", "elementor", "bricks", "wpbakery", "acf"]
            ).map((value) => (
              <option key={value} value={value}>{builderLabel(value)}</option>
            ))}
          </select>
        </label>
        <label>
          SEO-plugin
          <select value={seoPlugin} onChange={(event) => setSeoPlugin(event.target.value)}>
            <option value="yoast">Yoast SEO</option>
            <option value="rank_math">Rank Math</option>
            <option value="aioseo">All in One SEO</option>
          </select>
        </label>
        <label className="wide-field">
          Standaard templatepagina
          <select value={templateId} onChange={(event) => setTemplateId(event.target.value)}>
            <option value="">Kies een WordPress-pagina</option>
            {pages.map((page) => (
              <option key={page.id} value={page.id}>
                {page.title || page.url}
              </option>
            ))}
          </select>
        </label>
      </div>
      {slots.length > 0 && (
        <div className="template-block-section">
          <div className="template-block-heading">
            <h3>Blokken op de templatepagina</h3>
            <span>{slots.length} blokken</span>
          </div>
          <div className="template-block-list">
            {slots.map((slot, index) => (
              <article className="template-block-item" key={slot.path}>
                <span className="template-block-number">{index + 1}</span>
                <div>
                  <h4>{blockTitle(slot.label)}</h4>
                  {slot.preview && <p>{slot.preview}</p>}
                </div>
              </article>
            ))}
          </div>
          <details className="template-slot-mapping">
            <summary>AI-inhoud aan templateblokken koppelen</summary>
            <div className="settings-field-grid">
              {semanticSlots.map(([key, label]) => (
                <label key={key}>
                  {label}
                  <select
                    value={mapping[key] ?? ""}
                    onChange={(event) =>
                      setMapping((current) => ({ ...current, [key]: event.target.value }))
                    }
                  >
                    <option value="">Kies een templateblok</option>
                    {slots.map((slot) => (
                      <option key={slot.path} value={slot.path}>
                        {slot.label}
                      </option>
                    ))}
                  </select>
                </label>
              ))}
            </div>
          </details>
        </div>
      )}
      <div className="settings-actions">
        <button
          className="primary-button"
          disabled={busy || !templateId}
          onClick={save}
          type="button"
        >
          Paginapakket opslaan
        </button>
        <button
          className="secondary-button"
          disabled={busy || !configured}
          onClick={inspectTemplate}
          type="button"
        >
          Blokken ophalen
        </button>
        <button
          className="secondary-button"
          disabled={busy || !completeMapping}
          onClick={validate}
          type="button"
        >
          Paginapakket valideren
        </button>
      </div>
      <p className={`settings-message validation-${validationState}`}>
        Status: {validationLabel(validationState)}
      </p>
      {message && <p className="settings-message">{message}</p>}
    </section>
  );
}

function validationLabel(state: string) {
  return {
    unconfigured: "niet ingesteld",
    unvalidated: "nog niet gevalideerd",
    valid: "klaar voor conceptpagina's",
    invalid: "opnieuw instellen",
  }[state] ?? state;
}

function builderLabel(builder: string) {
  return {
    gutenberg: "Gutenberg",
    elementor: "Elementor",
    bricks: "Bricks",
    wpbakery: "WPBakery",
    acf: "ACF",
  }[builder] ?? builder;
}

function blockTitle(label: string) {
  const parts = label.split(" · ");
  return parts.at(-1) || label;
}
