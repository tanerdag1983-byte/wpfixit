import { useEffect, useState } from "react";

import { apiRequest } from "../../lib/api";

type CompanyProfileResponse = {
  configured: boolean;
  company_name?: string;
  description?: string;
  audience?: string;
  services?: string[];
  tone_of_voice?: string;
  custom_prompt?: string;
};

export function CompanyProfilePanel({ projectId }: { projectId: string }) {
  const [companyName, setCompanyName] = useState("");
  const [description, setDescription] = useState("");
  const [audience, setAudience] = useState("");
  const [services, setServices] = useState("");
  const [tone, setTone] = useState("");
  const [prompt, setPrompt] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    let active = true;
    apiRequest<CompanyProfileResponse>(`/projects/${projectId}/company-profile`)
      .then((profile) => {
        if (!active || !profile.configured) return;
        setCompanyName(profile.company_name ?? "");
        setDescription(profile.description ?? "");
        setAudience(profile.audience ?? "");
        setServices((profile.services ?? []).join(", "));
        setTone(profile.tone_of_voice ?? "");
        setPrompt(profile.custom_prompt ?? "");
      })
      .catch((error: unknown) => {
        if (active) {
          setMessage(
            error instanceof Error ? error.message : "Profiel laden is mislukt.",
          );
        }
      });
    return () => {
      active = false;
    };
  }, [projectId]);

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
      setMessage("Bedrijfsprofiel en projectprompt zijn opgeslagen.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Opslaan mislukt.");
    }
  }

  return (
    <section>
      <p className="eyebrow">Context voor aanbevelingen</p>
      <h2>Bedrijf- en websiteprofiel</h2>
      <p className="settings-intro">
        Deze informatie wordt alleen voor dit project aan AI-aanbevelingen
        toegevoegd. Een gewijzigde prompt of AI-modelkeuze maakt een nieuwe
        aanbevelingsversie.
      </p>
      <div className="settings-field-grid">
        <label>
          Bedrijfsnaam
          <input
            value={companyName}
            onChange={(event) => setCompanyName(event.target.value)}
          />
        </label>
        <label>
          Doelgroep
          <input
            value={audience}
            onChange={(event) => setAudience(event.target.value)}
          />
        </label>
        <label className="wide-field">
          Omschrijving
          <textarea
            value={description}
            onChange={(event) => setDescription(event.target.value)}
          />
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
          Projectprompt voor dit project
          <textarea
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            placeholder="Bijvoorbeeld: benadruk vakmanschap en gebruik alleen aantoonbare claims."
          />
          <span className="field-help">
            Deze prompt wordt alleen gebruikt voor dit project en niet gedeeld
            met andere projecten.
          </span>
        </label>
      </div>
      <button
        className="primary-button"
        disabled={!companyName}
        onClick={saveProfile}
        type="button"
      >
        Profiel opslaan
      </button>
      {message && <p className="settings-message">{message}</p>}
    </section>
  );
}
