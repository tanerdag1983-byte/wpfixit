import { useEffect, useState } from "react";

import { apiRequest } from "../../lib/api";

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

export function WordPressBridgePanel({ projectId }: { projectId: string }) {
  const [siteUrl, setSiteUrl] = useState("");
  const [secret, setSecret] = useState("");
  const [connection, setConnection] = useState<WordPressConnection | null>(null);
  const [pageCount, setPageCount] = useState<number | null>(null);
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
      {message && <p className="settings-message">{message}</p>}
    </section>
  );
}
