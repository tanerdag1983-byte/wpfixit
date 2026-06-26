import { useEffect, useState } from "react";

import { apiRequest } from "../../lib/api";

type DataForSeoConnection = {
  configured: boolean;
  login: string | null;
  enabled: boolean;
  last_test_status: string | null;
  last_test_message: string | null;
};

export function DataForSeoPanel({
  organizationId,
}: {
  organizationId: string;
}) {
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const [enabled, setEnabled] = useState(true);
  const [configured, setConfigured] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    let active = true;
    apiRequest<DataForSeoConnection>(
      `/organizations/${organizationId}/dataforseo-connection`,
    )
      .then((response) => {
        if (!active) return;
        setLogin(response.login ?? "");
        setEnabled(response.configured ? response.enabled : true);
        setConfigured(response.configured);
        setStatus(response.last_test_status);
      })
      .catch((error) => {
        if (active) {
          setMessage(
            error instanceof Error
              ? error.message
              : "DataForSEO-instellingen laden mislukt.",
          );
        }
      });
    return () => {
      active = false;
    };
  }, [organizationId]);

  async function save() {
    setBusy(true);
    setMessage("");
    try {
      const response = await apiRequest<DataForSeoConnection>(
        `/organizations/${organizationId}/dataforseo-connection`,
        {
          method: "PUT",
          body: JSON.stringify({
            login,
            password: password || undefined,
            enabled,
          }),
        },
      );
      setConfigured(response.configured);
      setStatus(response.last_test_status);
      setPassword("");
      setMessage("DataForSEO-verbinding is opgeslagen.");
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "DataForSEO opslaan mislukt.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function testConnection() {
    setBusy(true);
    setMessage("");
    try {
      const response = await apiRequest<DataForSeoConnection>(
        `/organizations/${organizationId}/dataforseo-connection/test`,
        { method: "POST" },
      );
      setStatus(response.last_test_status);
      setMessage("DataForSEO-verbinding is bereikbaar.");
    } catch (error) {
      setStatus("failed");
      setMessage(
        error instanceof Error
          ? error.message
          : "DataForSEO-verbinding testen mislukt.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      <p className="eyebrow">Zoekwoorddata</p>
      <h2>DataForSEO</h2>
      <p className="settings-intro">
        Gebruik live zoekvolume, concurrentie, CPC en zoekintentie om nieuwe
        SEO-kansen per project te vinden. De credentials worden versleuteld
        opgeslagen.
      </p>

      {configured && (
        <div className="connection-list">
          <div className="connection-row">
            <div>
              <strong>{login}</strong>
              <span>DataForSEO Labs · Nederland · Nederlands</span>
            </div>
            <span className={`connection-status ${status ?? ""}`}>
              {status === "connected"
                ? "Verbonden"
                : status === "failed"
                  ? "Mislukt"
                  : enabled
                    ? "Ingesteld"
                    : "Uitgeschakeld"}
            </span>
            <button
              className="secondary-button"
              disabled={busy || !enabled}
              onClick={testConnection}
              type="button"
            >
              Verbinding testen
            </button>
          </div>
        </div>
      )}

      <div className="settings-field-grid connection-form">
        <label>
          DataForSEO login
          <input
            type="email"
            value={login}
            onChange={(event) => setLogin(event.target.value)}
            placeholder="account@example.com"
          />
        </label>
        <label>
          DataForSEO wachtwoord
          <input
            type="password"
            autoComplete="new-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            placeholder={
              configured
                ? "Leeg laten om huidig wachtwoord te behouden"
                : "DataForSEO API-wachtwoord"
            }
          />
        </label>
        <label className="wide-field settings-checkbox">
          <input
            type="checkbox"
            checked={enabled}
            onChange={(event) => setEnabled(event.target.checked)}
          />
          Zoekwoordonderzoek inschakelen
        </label>
      </div>
      <button
        className="primary-button"
        disabled={busy || !login || (!configured && !password)}
        onClick={save}
        type="button"
      >
        {busy ? "Bezig..." : "Verbinding opslaan"}
      </button>
      {message && <p className="settings-message">{message}</p>}
    </section>
  );
}
