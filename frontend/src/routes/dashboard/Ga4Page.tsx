import { Activity, ArrowUpRight, CircleDollarSign, Users } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { apiRequest } from "../../lib/api";

type Ga4PagePerformance = {
  date: string;
  page_path: string;
  sessions: number;
  users: number;
  engagement_rate: number;
  conversions: number;
  revenue: number;
};

type Ga4TrafficSource = {
  date: string;
  source: string;
  medium: string;
  campaign: string | null;
  sessions: number;
  users: number;
  engagement_rate: number;
  conversions: number;
  revenue: number;
};

type Ga4Data = {
  pages: Ga4PagePerformance[];
  traffic_sources: Ga4TrafficSource[];
};

type Ga4Property = {
  account: string | null;
  account_display_name: string | null;
  property: string;
  display_name: string;
};

const connectionStorageKey = "wpfixpilot.googleConnectionId";
const returnRouteStorageKey = "wpfixpilot.googleReturnRoute";
const numberFormatter = new Intl.NumberFormat("nl-NL");
const percentFormatter = new Intl.NumberFormat("nl-NL", {
  maximumFractionDigits: 1,
  style: "percent",
});
const currencyFormatter = new Intl.NumberFormat("nl-NL", {
  currency: "EUR",
  maximumFractionDigits: 0,
  style: "currency",
});

export function Ga4Page({ projectId }: { projectId: string }) {
  const [data, setData] = useState<Ga4Data>({
    pages: [],
    traffic_sources: [],
  });
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [googleConnectionId, setGoogleConnectionId] = useState(
    () => sessionStorage.getItem(connectionStorageKey) ?? "",
  );
  const [properties, setProperties] = useState<Ga4Property[]>([]);
  const [selectedProperty, setSelectedProperty] = useState("");
  const [message, setMessage] = useState("");

  async function loadData() {
    setLoading(true);
    try {
      const response = await apiRequest<Ga4Data>(`/projects/${projectId}/ga4-data`);
      setData(response);
      setMessage("");
    } catch (error) {
      setMessage((error as Error).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadData();
  }, [projectId]);

  useEffect(() => {
    if (!googleConnectionId) return;
    apiRequest<{ items: Ga4Property[] }>(
      `/google/connections/${googleConnectionId}/ga4-properties`,
    )
      .then((response) => {
        setProperties(response.items);
        setSelectedProperty(response.items[0]?.property ?? "");
      })
      .catch((error: Error) => setMessage(error.message));
  }, [googleConnectionId]);

  async function syncData() {
    setSyncing(true);
    try {
      await apiRequest(`/projects/${projectId}/sync-ga4`, { method: "POST" });
      await loadData();
      setMessage("GA4-data is bijgewerkt.");
    } catch (error) {
      setMessage((error as Error).message);
    } finally {
      setSyncing(false);
    }
  }

  async function startGoogleConnection() {
    sessionStorage.setItem(returnRouteStorageKey, "ga4");
    try {
      const response = await apiRequest<{ authorization_url: string }>(
        `/projects/${projectId}/connect-search-console`,
        { method: "POST" },
      );
      window.location.assign(response.authorization_url);
    } catch (error) {
      setMessage((error as Error).message);
    }
  }

  async function bindProperty() {
    const property = properties.find((item) => item.property === selectedProperty);
    if (!googleConnectionId || !property) return;
    try {
      await apiRequest(`/projects/${projectId}/connect-ga4`, {
        body: JSON.stringify({
          account_id: property.account,
          display_name: property.display_name,
          google_connection_id: googleConnectionId,
          property_id: property.property,
        }),
        method: "POST",
      });
      sessionStorage.removeItem(connectionStorageKey);
      setGoogleConnectionId("");
      setMessage("GA4-property is gekoppeld.");
      await syncData();
    } catch (error) {
      setMessage((error as Error).message);
    }
  }

  const metrics = useMemo(() => {
    const sessions = data.pages.reduce((total, row) => total + row.sessions, 0);
    const users = data.pages.reduce((total, row) => total + row.users, 0);
    const conversions = data.pages.reduce(
      (total, row) => total + row.conversions,
      0,
    );
    const revenue = data.pages.reduce((total, row) => total + row.revenue, 0);
    const weightedEngagement = data.pages.reduce(
      (total, row) => total + row.engagement_rate * row.sessions,
      0,
    );
    return [
      { label: "Sessies", value: numberFormatter.format(sessions) },
      { label: "Gebruikers", value: numberFormatter.format(users) },
      {
        label: "Engagement",
        value: percentFormatter.format(weightedEngagement / sessions || 0),
      },
      { label: "Conversies", value: numberFormatter.format(conversions) },
      { label: "Omzet", value: currencyFormatter.format(revenue) },
    ];
  }, [data.pages]);

  return (
    <section className="data-page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Gedrag en resultaat</p>
          <h1>Google Analytics 4</h1>
          <p className="subtitle">
            Verkeer, engagement, conversies en omzet per pagina en kanaal.
          </p>
        </div>
        <button
          className="sync-button"
          disabled={syncing}
          onClick={syncData}
          type="button"
        >
          <Activity size={16} />
          {syncing ? "Synchroniseren..." : "Data synchroniseren"}
        </button>
      </div>

      {message && <p className="inline-status">{message}</p>}

      <section className="integration-panel">
        <div>
          <p className="eyebrow">Google koppeling</p>
          <h2>GA4 property</h2>
          <p>
            Koppel een GA4-property om sessies, engagement, conversies en omzet
            te importeren.
          </p>
        </div>
        {properties.length > 0 ? (
          <div className="integration-actions">
            <label>
              GA4 property
              <select
                aria-label="GA4 property"
                value={selectedProperty}
                onChange={(event) => setSelectedProperty(event.target.value)}
              >
                {properties.map((property) => (
                  <option value={property.property} key={property.property}>
                    {property.display_name}
                  </option>
                ))}
              </select>
            </label>
            <button className="sync-button" onClick={bindProperty} type="button">
              Property koppelen
            </button>
          </div>
        ) : (
          <button
            className="sync-button"
            onClick={startGoogleConnection}
            type="button"
          >
            Google koppelen
          </button>
        )}
      </section>

      <div className="data-metrics" aria-busy={loading}>
        {metrics.map((metric) => (
          <div key={metric.label}>
            <span>{metric.label}</span>
            <strong>{loading ? "..." : metric.value}</strong>
            <small>Live API</small>
          </div>
        ))}
      </div>

      <div className="data-grid">
        <section>
          <div className="section-heading">
            <div>
              <p className="eyebrow">Pagina's</p>
              <h2>Sessies en conversies</h2>
            </div>
            <Users size={19} />
          </div>
          <div className="query-table">
            <div className="query-row header">
              <span>Pagina</span>
              <span>Sessies</span>
              <span>Engagement</span>
              <span>Conversies</span>
            </div>
            {data.pages.length === 0 && !loading ? (
              <p className="empty-state">
                Nog geen GA4-data. Koppel Google Analytics en synchroniseer.
              </p>
            ) : (
              data.pages.slice(0, 6).map((page) => (
                <button className="query-row" type="button" key={page.page_path}>
                  <strong>{page.page_path}</strong>
                  <span>{numberFormatter.format(page.sessions)}</span>
                  <span>{percentFormatter.format(page.engagement_rate)}</span>
                  <span>{numberFormatter.format(page.conversions)}</span>
                </button>
              ))
            )}
          </div>
        </section>

        <section className="query-panel">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Acquisitie</p>
              <h2>Verkeersbronnen</h2>
            </div>
            <CircleDollarSign size={19} />
          </div>
          <div className="query-table">
            <div className="query-row header">
              <span>Bron / medium</span>
              <span>Sessies</span>
              <span>Engagement</span>
              <span>Conversies</span>
            </div>
            {data.traffic_sources.length === 0 && !loading ? (
              <p className="empty-state">Nog geen verkeersbronnen beschikbaar.</p>
            ) : (
              data.traffic_sources.slice(0, 8).map((row) => (
                <button
                  className="query-row"
                  type="button"
                  key={`${row.source}-${row.medium}-${row.campaign ?? ""}`}
                >
                  <strong>
                    {row.source} / {row.medium}
                  </strong>
                  <span>{numberFormatter.format(row.sessions)}</span>
                  <span>{percentFormatter.format(row.engagement_rate)}</span>
                  <span>
                    {numberFormatter.format(row.conversions)}{" "}
                    <ArrowUpRight size={13} />
                  </span>
                </button>
              ))
            )}
          </div>
        </section>
      </div>
    </section>
  );
}
