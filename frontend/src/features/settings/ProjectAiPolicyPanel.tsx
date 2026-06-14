import { useEffect, useState } from "react";

import { apiRequest } from "../../lib/api";
import type { AiConnection } from "./AiConnectionsPanel";

type PolicyResponse = {
  configured: boolean;
  primary?: { connection_id: string; model: string };
  fallback?: { connection_id: string; model: string } | null;
};

export function ProjectAiPolicyPanel({
  organizationId,
  projectId,
  connectionsRevision = 0,
}: {
  organizationId: string;
  projectId: string;
  connectionsRevision?: number;
}) {
  const [connections, setConnections] = useState<AiConnection[]>([]);
  const [primaryId, setPrimaryId] = useState("");
  const [primaryModel, setPrimaryModel] = useState("");
  const [fallbackId, setFallbackId] = useState("");
  const [fallbackModel, setFallbackModel] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    let active = true;
    Promise.all([
      apiRequest<{ items: AiConnection[] }>(
        `/organizations/${organizationId}/ai-connections`,
      ),
      apiRequest<PolicyResponse>(`/projects/${projectId}/ai-policy`),
    ])
      .then(([connectionResponse, policy]) => {
        if (!active) return;
        const enabled = connectionResponse.items.filter(
          (connection) => connection.enabled,
        );
        setConnections(enabled);
        if (policy.configured && policy.primary) {
          setPrimaryId(policy.primary.connection_id);
          setPrimaryModel(policy.primary.model);
          setFallbackId(policy.fallback?.connection_id ?? "");
          setFallbackModel(policy.fallback?.model ?? "");
        } else if (enabled[0]) {
          setPrimaryId(enabled[0].id);
          setPrimaryModel(enabled[0].default_model ?? "");
        }
      })
      .catch((error: unknown) => {
        if (active) {
          setMessage(
            error instanceof Error
              ? error.message
              : "Modelbeleid laden is mislukt.",
          );
        }
      });
    return () => {
      active = false;
    };
  }, [connectionsRevision, organizationId, projectId]);

  function changePrimary(connectionId: string) {
    setPrimaryId(connectionId);
    const connection = connections.find((item) => item.id === connectionId);
    setPrimaryModel(connection?.default_model ?? "");
  }

  function changeFallback(connectionId: string) {
    setFallbackId(connectionId);
    const connection = connections.find((item) => item.id === connectionId);
    setFallbackModel(connection?.default_model ?? "");
  }

  async function savePolicy() {
    try {
      await apiRequest(`/projects/${projectId}/ai-policy`, {
        method: "PUT",
        body: JSON.stringify({
          primary_connection_id: primaryId,
          primary_model: primaryModel,
          fallback_connection_id: fallbackId || null,
          fallback_model: fallbackId ? fallbackModel : null,
        }),
      });
      setMessage("Modelbeleid voor dit project is opgeslagen.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Opslaan mislukt.");
    }
  }

  return (
    <section>
      <p className="eyebrow">Projectinstelling</p>
      <h2>Modelbeleid voor dit project</h2>
      <p className="settings-intro">
        Kies het standaardmodel voor aanbevelingen en optioneel een fallback als
        de eerste provider tijdelijk niet beschikbaar is.
      </p>
      {connections.length === 0 ? (
        <p className="settings-empty">
          Voeg eerst hierboven een actieve AI-verbinding toe.
        </p>
      ) : (
        <>
          <div className="settings-field-grid">
            <label>
              Primaire verbinding
              <select
                value={primaryId}
                onChange={(event) => changePrimary(event.target.value)}
              >
                {connections.map((connection) => (
                  <option key={connection.id} value={connection.id}>
                    {connection.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Primair model
              <input
                value={primaryModel}
                onChange={(event) => setPrimaryModel(event.target.value)}
              />
            </label>
            <label>
              Fallbackverbinding
              <select
                value={fallbackId}
                onChange={(event) => changeFallback(event.target.value)}
              >
                <option value="">Geen fallback</option>
                {connections.map((connection) => (
                  <option key={connection.id} value={connection.id}>
                    {connection.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Fallbackmodel
              <input
                disabled={!fallbackId}
                value={fallbackModel}
                onChange={(event) => setFallbackModel(event.target.value)}
              />
            </label>
          </div>
          <button
            className="primary-button"
            disabled={!primaryId || !primaryModel}
            onClick={savePolicy}
            type="button"
          >
            Modelbeleid opslaan
          </button>
        </>
      )}
      {message && <p className="settings-message">{message}</p>}
    </section>
  );
}
