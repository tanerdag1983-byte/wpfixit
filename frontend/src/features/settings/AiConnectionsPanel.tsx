import { useCallback, useEffect, useState } from "react";

import { apiRequest } from "../../lib/api";

type Provider = "openai" | "anthropic" | "gemini" | "openai_compatible";

export type AiConnection = {
  id: string;
  name: string;
  provider: Provider;
  base_url: string;
  default_model?: string | null;
  enabled: boolean;
  configured: boolean;
  last_test_status?: string | null;
  last_test_message?: string | null;
};

const providers: Record<
  Provider,
  { label: string; baseUrl: string; model: string }
> = {
  openai: {
    label: "OpenAI",
    baseUrl: "https://api.openai.com/v1",
    model: "gpt-5.4-mini",
  },
  anthropic: {
    label: "Anthropic",
    baseUrl: "https://api.anthropic.com/v1",
    model: "claude-sonnet-4-5",
  },
  gemini: {
    label: "Google Gemini",
    baseUrl: "https://generativelanguage.googleapis.com/v1beta",
    model: "gemini-2.5-flash",
  },
  openai_compatible: {
    label: "OpenAI-compatible",
    baseUrl: "https://",
    model: "",
  },
};

export function AiConnectionsPanel({
  organizationId,
  onConnectionsChange,
}: {
  organizationId: string;
  onConnectionsChange?: () => void;
}) {
  const [connections, setConnections] = useState<AiConnection[]>([]);
  const [name, setName] = useState("");
  const [provider, setProvider] = useState<Provider>("openai");
  const [baseUrl, setBaseUrl] = useState(providers.openai.baseUrl);
  const [model, setModel] = useState(providers.openai.model);
  const [apiKey, setApiKey] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [message, setMessage] = useState("");

  const loadConnections = useCallback(async () => {
    const response = await apiRequest<{ items: AiConnection[] }>(
      `/organizations/${organizationId}/ai-connections`,
    );
    setConnections(response.items);
  }, [organizationId]);

  useEffect(() => {
    let active = true;
    apiRequest<{ items: AiConnection[] }>(
      `/organizations/${organizationId}/ai-connections`,
    )
      .then((response) => {
        if (active) setConnections(response.items);
      })
      .catch((error: unknown) => {
        if (active) {
          setMessage(
            error instanceof Error
              ? error.message
              : "AI-verbindingen laden is mislukt.",
          );
        }
      });
    return () => {
      active = false;
    };
  }, [organizationId]);

  function selectProvider(nextProvider: Provider) {
    setProvider(nextProvider);
    setBaseUrl(providers[nextProvider].baseUrl);
    setModel(providers[nextProvider].model);
  }

  function resetForm() {
    setName("");
    setProvider("openai");
    setBaseUrl(providers.openai.baseUrl);
    setModel(providers.openai.model);
    setApiKey("");
    setEditingId(null);
  }

  function editConnection(connection: AiConnection) {
    setEditingId(connection.id);
    setName(connection.name);
    setProvider(connection.provider);
    setBaseUrl(connection.base_url);
    setModel(connection.default_model ?? "");
    setApiKey("");
    setMessage("");
  }

  async function saveConnection() {
    setMessage("");
    try {
      const saved = await apiRequest<AiConnection>(
        editingId
          ? `/organizations/${organizationId}/ai-connections/${editingId}`
          : `/organizations/${organizationId}/ai-connections`,
        {
          method: editingId ? "PUT" : "POST",
          body: JSON.stringify({
            name,
            provider,
            base_url: baseUrl,
            default_model: model || null,
            ...(apiKey ? { api_key: apiKey } : {}),
            enabled: true,
          }),
        },
      );
      setConnections((current) =>
        editingId
          ? current.map((item) => (item.id === editingId ? saved : item))
          : [...current, saved],
      );
      setMessage(
        editingId
          ? "AI-verbinding is bijgewerkt."
          : "AI-verbinding is versleuteld opgeslagen.",
      );
      resetForm();
      onConnectionsChange?.();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Opslaan mislukt.");
    }
  }

  async function testConnection(connection: AiConnection) {
    try {
      const tested = await apiRequest<AiConnection>(
        `/organizations/${organizationId}/ai-connections/${connection.id}/test`,
        {
          method: "POST",
          body: JSON.stringify({ model: connection.default_model }),
        },
      );
      setConnections((current) =>
        current.map((item) => (item.id === connection.id ? tested : item)),
      );
      setMessage(`${connection.name} is bereikbaar.`);
    } catch (error) {
      await loadConnections();
      setMessage(
        error instanceof Error ? error.message : "Verbinding testen mislukt.",
      );
    }
  }

  async function deleteConnection(connection: AiConnection) {
    try {
      await apiRequest(
        `/organizations/${organizationId}/ai-connections/${connection.id}`,
        { method: "DELETE" },
      );
      await loadConnections();
      setMessage(`${connection.name} is verwijderd.`);
      onConnectionsChange?.();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Verwijderen mislukt.");
    }
  }

  return (
    <section>
      <p className="eyebrow">Organisatiebreed</p>
      <h2>AI-verbindingen</h2>
      <p className="settings-intro">
        Koppel meerdere modellen. API-keys worden versleuteld bewaard en nooit
        teruggestuurd naar de browser.
      </p>

      <div className="connection-list">
        {connections.length === 0 && (
          <p className="settings-empty">Nog geen AI-provider gekoppeld.</p>
        )}
        {connections.map((connection) => (
          <div className="connection-row" key={connection.id}>
            <div>
              <strong>{connection.name}</strong>
              <span>
                {providers[connection.provider].label}
                {connection.default_model
                  ? ` · ${connection.default_model}`
                  : ""}
              </span>
              {connection.last_test_message && (
                <span className="connection-test-message">
                  Laatste test: {connection.last_test_message}
                </span>
              )}
            </div>
            <span
              className={`connection-status ${connection.last_test_status ?? ""}`}
            >
              {connection.last_test_status === "connected"
                ? "Verbonden"
                : connection.last_test_status === "failed"
                  ? "Mislukt"
                : connection.enabled
                  ? "Actief"
                  : "Uitgeschakeld"}
            </span>
            <div className="connection-actions">
              <button
                className="secondary-button"
                onClick={() => testConnection(connection)}
                type="button"
              >
                {connection.name} testen
              </button>
              <button
                className="text-button"
                onClick={() => editConnection(connection)}
                type="button"
              >
                {connection.name} bewerken
              </button>
              <button
                className="text-button danger-button"
                onClick={() => deleteConnection(connection)}
                type="button"
              >
                Verwijderen
              </button>
            </div>
          </div>
        ))}
      </div>

      <div className="settings-field-grid connection-form">
        <label>
          Naam verbinding
          <input
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Bijvoorbeeld: Gemini SEO"
          />
        </label>
        <label>
          Provider
          <select
            value={provider}
            onChange={(event) => selectProvider(event.target.value as Provider)}
          >
            {Object.entries(providers).map(([value, details]) => (
              <option key={value} value={value}>
                {details.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          API base URL
          <input
            value={baseUrl}
            onChange={(event) => setBaseUrl(event.target.value)}
          />
        </label>
        <label>
          Standaardmodel
          <input value={model} onChange={(event) => setModel(event.target.value)} />
        </label>
        <label className="wide-field">
          API-key
          <input
            type="password"
            autoComplete="new-password"
            value={apiKey}
            onChange={(event) => setApiKey(event.target.value)}
            placeholder="Wordt versleuteld opgeslagen"
          />
        </label>
      </div>
      <button
        className="primary-button"
        disabled={!name || !baseUrl || (!editingId && !apiKey)}
        onClick={saveConnection}
        type="button"
      >
        {editingId ? "Wijzigingen opslaan" : "Verbinding toevoegen"}
      </button>
      {editingId && (
        <button
          className="text-button cancel-edit-button"
          onClick={resetForm}
          type="button"
        >
          Annuleren
        </button>
      )}
      {message && <p className="settings-message">{message}</p>}
    </section>
  );
}
