import { useEffect, useState } from "react";

import { apiRequest } from "../../lib/api";

type AiSettingsResponse = {
  configured: boolean;
  provider?: string;
  base_url?: string;
  model?: string;
};

type CompanyProfileResponse = {
  configured: boolean;
  company_name?: string;
  description?: string;
  audience?: string;
  services?: string[];
  tone_of_voice?: string;
  custom_prompt?: string;
};

export function AiSettingsPanel({
  organizationId,
  projectId,
}: {
  organizationId: string;
  projectId: string;
}) {
  const [provider, setProvider] = useState("openai");
  const [baseUrl, setBaseUrl] = useState("https://api.openai.com/v1");
  const [model, setModel] = useState("gpt-5.4-mini");
  const [apiKey, setApiKey] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [description, setDescription] = useState("");
  const [audience, setAudience] = useState("");
  const [services, setServices] = useState("");
  const [tone, setTone] = useState("");
  const [prompt, setPrompt] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    let active = true;
    setMessage("");
    setCompanyName("");
    setDescription("");
    setAudience("");
    setServices("");
    setTone("");
    setPrompt("");
    Promise.all([
      apiRequest<AiSettingsResponse>(
        `/organizations/${organizationId}/ai-settings`,
      ),
      apiRequest<CompanyProfileResponse>(
        `/projects/${projectId}/company-profile`,
      ),
    ])
      .then(([aiSettings, companyProfile]) => {
        if (!active) return;
        if (aiSettings.configured) {
          setProvider(aiSettings.provider ?? "openai");
          setBaseUrl(aiSettings.base_url ?? "https://api.openai.com/v1");
          setModel(aiSettings.model ?? "gpt-5.4-mini");
        }
        if (companyProfile.configured) {
          setCompanyName(companyProfile.company_name ?? "");
          setDescription(companyProfile.description ?? "");
          setAudience(companyProfile.audience ?? "");
          setServices((companyProfile.services ?? []).join(", "));
          setTone(companyProfile.tone_of_voice ?? "");
          setPrompt(companyProfile.custom_prompt ?? "");
        }
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [organizationId, projectId]);

  async function saveAi() {
    try {
      await apiRequest(`/organizations/${organizationId}/ai-settings`, {
        method: "PUT",
        body: JSON.stringify({
          provider,
          base_url: baseUrl,
          model,
          ...(apiKey ? { api_key: apiKey } : {}),
        }),
      });
      setApiKey("");
      setMessage("AI-koppeling is veilig opgeslagen.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Opslaan mislukt.");
    }
  }

  async function saveProfile() {
    try {
      await apiRequest(`/projects/${projectId}/company-profile`, {
        method: "PUT",
        body: JSON.stringify({
          company_name: companyName,
          description,
          audience,
          services: services
            .split(",")
            .map((item) => item.trim())
            .filter(Boolean),
          tone_of_voice: tone,
          custom_prompt: prompt,
        }),
      });
      setMessage("Bedrijfsprofiel en prompt zijn opgeslagen.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Opslaan mislukt.");
    }
  }

  async function testConnection() {
    try {
      await apiRequest(`/organizations/${organizationId}/ai-settings/test`, {
        method: "POST",
      });
      setMessage("AI-provider en model zijn bereikbaar.");
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "Verbinding testen mislukt.",
      );
    }
  }

  return (
    <div className="ai-settings">
      <section>
        <p className="eyebrow">AI-provider</p>
        <h2>Koppel je eigen model</h2>
        <div className="settings-field-grid">
          <label>
            Provider
            <select value={provider} onChange={(event) => setProvider(event.target.value)}>
              <option value="openai">OpenAI</option>
              <option value="openai_compatible">OpenAI-compatible API</option>
            </select>
          </label>
          <label>
            API base URL
            <input value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} />
          </label>
          <label>
            Model
            <input value={model} onChange={(event) => setModel(event.target.value)} />
          </label>
          <label>
            API-key
            <input
              type="password"
              autoComplete="off"
              value={apiKey}
              onChange={(event) => setApiKey(event.target.value)}
              placeholder="Wordt versleuteld opgeslagen"
            />
          </label>
        </div>
        <div className="settings-actions">
          <button className="primary-button" onClick={saveAi} type="button">
            AI-koppeling opslaan
          </button>
          <button
            className="secondary-button"
            onClick={testConnection}
            type="button"
          >
            Verbinding testen
          </button>
        </div>
      </section>

      <section>
        <p className="eyebrow">Context voor aanbevelingen</p>
        <h2>Bedrijf- en websiteprofiel</h2>
        <div className="settings-field-grid">
          <label>
            Bedrijfsnaam
            <input value={companyName} onChange={(event) => setCompanyName(event.target.value)} />
          </label>
          <label>
            Doelgroep
            <input value={audience} onChange={(event) => setAudience(event.target.value)} />
          </label>
          <label className="wide-field">
            Omschrijving
            <textarea value={description} onChange={(event) => setDescription(event.target.value)} />
          </label>
          <label>
            Diensten
            <input
              value={services}
              onChange={(event) => setServices(event.target.value)}
              placeholder="Revisie, diagnose, onderhoud"
            />
          </label>
          <label>
            Tone of voice
            <input value={tone} onChange={(event) => setTone(event.target.value)} />
          </label>
          <label className="wide-field">
            Bedrijfsprofiel prompt
            <textarea
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              placeholder="Bijvoorbeeld: benadruk vakmanschap, schrijf helder en vermijd onbewezen claims."
            />
          </label>
        </div>
        <button className="primary-button" onClick={saveProfile} type="button">
          Profiel en prompt opslaan
        </button>
      </section>
      {message && <p className="settings-message">{message}</p>}
    </div>
  );
}
