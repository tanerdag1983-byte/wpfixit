import { useEffect, useState } from "react";

import { apiBaseUrl, apiRequest } from "../../lib/api";

type WordPressConnection = {
  project_id: string;
  site_url: string;
  plugin_version?: string | null;
  seo_plugin?: string | null;
  health_state: string;
};

type WordPressPagesResponse = {
  count: number;
};

type OutboundCredential = {
  id: string;
  project_id: string;
  site_url: string;
  last_seen_at?: string | null;
  revoked_at?: string | null;
};

type OutboundCredentialCreated = OutboundCredential & { key: string };

export function WordPressBridgePanel({ projectId }: { projectId: string }) {
  const [siteUrl, setSiteUrl] = useState("");
  const [secret, setSecret] = useState("");
  const [connection, setConnection] = useState<WordPressConnection | null>(null);
  const [pageCount, setPageCount] = useState<number | null>(null);
  const [outboundCredential, setOutboundCredential] =
    useState<OutboundCredential | null>(null);
  const [oneTimeKey, setOneTimeKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    let active = true;
    apiRequest<WordPressConnection>(`/projects/${projectId}/wordpress-connection`)
      .then((response) => {
        if (!active) return;
        setConnection(response);
        setSiteUrl(response.site_url);
        setMessage("");
      })
      .catch(() => {
        if (active) setConnection(null);
      });
    apiRequest<WordPressPagesResponse>(`/projects/${projectId}/wordpress-pages`)
      .then((response) => {
        if (active) setPageCount(response.count);
      })
      .catch(() => {
        if (active) setPageCount(null);
      });
    apiRequest<OutboundCredential>(
      `/projects/${projectId}/wordpress-outbound-credential`,
    )
      .then((response) => {
        if (!active) return;
        setOutboundCredential(response);
        if (!siteUrl) setSiteUrl(response.site_url);
      })
      .catch(() => {
        if (active) setOutboundCredential(null);
      });
    return () => {
      active = false;
    };
  }, [projectId]);

  async function connect() {
    setBusy(true);
    setMessage("");
    try {
      const response = await apiRequest<WordPressConnection>(
        `/projects/${projectId}/wordpress-connect`,
        {
          method: "POST",
          body: JSON.stringify({ site_url: siteUrl, secret }),
        },
      );
      setConnection(response);
      setSecret("");
      setMessage("WordPress bridge is verbonden.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Koppelen mislukt.");
    } finally {
      setBusy(false);
    }
  }

  async function syncPages() {
    setBusy(true);
    setMessage("");
    try {
      const response = await apiRequest<{ saved_count: number }>(
        `/projects/${projectId}/sync-pages`,
        { method: "POST" },
      );
      setPageCount(response.saved_count);
      setMessage(`${response.saved_count} WordPress-pagina's gesynchroniseerd.`);
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "Pagina's synchroniseren mislukt.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function runAudit() {
    setBusy(true);
    setMessage("");
    try {
      const response = await apiRequest<{ audited_count: number }>(
        `/projects/${projectId}/audit`,
        { method: "POST" },
      );
      setMessage(`${response.audited_count} WordPress-pagina's geaudit.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Audit draaien mislukt.");
    } finally {
      setBusy(false);
    }
  }

  async function createProjectKey() {
    setBusy(true);
    setMessage("");
    try {
      const response = await apiRequest<OutboundCredentialCreated>(
        `/projects/${projectId}/wordpress-outbound-credential`,
        {
          method: "POST",
          body: JSON.stringify({ site_url: siteUrl }),
        },
      );
      setOutboundCredential(response);
      setOneTimeKey(response.key);
      setMessage("Projectkey aangemaakt.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Projectkey maken mislukt.");
    } finally {
      setBusy(false);
    }
  }

  async function rotateProjectKey() {
    if (
      !window.confirm(
        "De huidige projectkey stopt direct met werken. Projectkey vernieuwen?",
      )
    ) {
      return;
    }
    setBusy(true);
    setMessage("");
    try {
      const response = await apiRequest<OutboundCredentialCreated>(
        `/projects/${projectId}/wordpress-outbound-credential/rotate`,
        { method: "POST" },
      );
      setOutboundCredential(response);
      setOneTimeKey(response.key);
      setMessage("Projectkey vernieuwd. De vorige key werkt niet meer.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Projectkey vernieuwen mislukt.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      <p className="eyebrow">WordPress bridge</p>
      <h2>Website koppelen</h2>
      <p className="settings-intro">
        Installeer de bridge plugin in WordPress, kopieer daar de secret en koppel
        daarna de site hier. Daarna kan WP FixPilot pagina's synchroniseren en
        wijzigingen gecontroleerd publiceren.
      </p>

      {connection && (
        <div className="connection-list">
          <div className="connection-row">
            <div>
              <strong>{connection.site_url}</strong>
              <span>
                Plugin {connection.plugin_version ?? "onbekend"} · SEO{" "}
                {connection.seo_plugin ?? "niet gedetecteerd"}
              </span>
            </div>
            <span className={`connection-status ${connection.health_state}`}>
              {connection.health_state === "connected" ? "Verbonden" : connection.health_state}
            </span>
            <div className="connection-actions">
              <button
                className="secondary-button"
                disabled={busy}
                onClick={syncPages}
                type="button"
              >
                Pagina's synchroniseren
              </button>
              <button
                className="secondary-button"
                disabled={busy}
                onClick={runAudit}
                type="button"
              >
                SEO-audit draaien
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="settings-field-grid connection-form">
        <label>
          WordPress URL
          <input
            type="url"
            value={siteUrl}
            onChange={(event) => setSiteUrl(event.target.value)}
            placeholder="https://voorbeeld.nl"
          />
        </label>
        <label>
          Bridge secret
          <input
            type="password"
            autoComplete="new-password"
            value={secret}
            onChange={(event) => setSecret(event.target.value)}
            placeholder="Kopieer uit WordPress > Instellingen > WP FixPilot"
          />
        </label>
      </div>
      <button
        className="primary-button"
        disabled={busy || !siteUrl || !secret}
        onClick={connect}
        type="button"
      >
        {busy ? "Bezig..." : connection ? "Opnieuw koppelen" : "WordPress koppelen"}
      </button>
      {pageCount !== null && (
        <p className="settings-empty">{pageCount} WordPress-pagina's bekend.</p>
      )}
      <div className="settings-divider" />
      <p className="eyebrow">Uitgaande concepttaken</p>
      <h3>WordPress projectkey</h3>
      <div className="settings-field-grid connection-form">
        <label>
          Backend URL
          <input aria-label="Backend URL" readOnly value={apiBaseUrl} />
        </label>
        <label>
          Project ID
          <input aria-label="Project ID" readOnly value={projectId} />
        </label>
      </div>
      {outboundCredential && (
        <p className="settings-empty">
          Gekoppeld aan {outboundCredential.site_url}
          {outboundCredential.last_seen_at ? " · recent contact" : ""}
        </p>
      )}
      {oneTimeKey && (
        <label>
          Eenmalige projectkey
          <input aria-label="Eenmalige projectkey" readOnly value={oneTimeKey} />
          <span className="settings-empty">Deze key wordt niet opnieuw getoond.</span>
        </label>
      )}
      <button
        className={outboundCredential ? "secondary-button" : "primary-button"}
        disabled={busy || (!outboundCredential && !siteUrl)}
        onClick={outboundCredential ? rotateProjectKey : createProjectKey}
        type="button"
      >
        {outboundCredential ? "Projectkey vernieuwen" : "Projectkey maken"}
      </button>
      {message && <p className="settings-message">{message}</p>}
    </section>
  );
}
