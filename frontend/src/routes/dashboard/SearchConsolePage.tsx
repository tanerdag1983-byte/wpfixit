import {
  ArrowUpRight,
  MousePointerClick,
  Search,
  TrendingUp,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { apiRequest } from "../../lib/api";

type GscPagePerformance = {
  date: string;
  page_url: string;
  clicks: number;
  impressions: number;
  ctr: number;
  average_position: number;
};

type GscQuery = {
  date: string;
  query: string;
  page_url: string;
  clicks: number;
  impressions: number;
  ctr: number;
  average_position: number;
};

type GscData = {
  pages: GscPagePerformance[];
  queries: GscQuery[];
};

type GscProperty = {
  siteUrl: string;
  permissionLevel?: string;
};

const connectionStorageKey = "wpfixpilot.googleConnectionId";
const returnRouteStorageKey = "wpfixpilot.googleReturnRoute";
const numberFormatter = new Intl.NumberFormat("nl-NL");
const percentFormatter = new Intl.NumberFormat("nl-NL", {
  maximumFractionDigits: 1,
  style: "percent",
});
const decimalFormatter = new Intl.NumberFormat("nl-NL", {
  maximumFractionDigits: 1,
});

export function SearchConsolePage({ projectId }: { projectId: string }) {
  const [data, setData] = useState<GscData>({ pages: [], queries: [] });
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [googleConnectionId, setGoogleConnectionId] = useState(
    () => sessionStorage.getItem(connectionStorageKey) ?? "",
  );
  const [properties, setProperties] = useState<GscProperty[]>([]);
  const [selectedProperty, setSelectedProperty] = useState("");
  const [message, setMessage] = useState("");

  async function loadData() {
    setLoading(true);
    try {
      const response = await apiRequest<GscData>(
        `/projects/${projectId}/search-console-data`,
      );
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
    apiRequest<{ items: GscProperty[] }>(
      `/google/connections/${googleConnectionId}/search-console-properties`,
    )
      .then((response) => {
        setProperties(response.items);
        setSelectedProperty(response.items[0]?.siteUrl ?? "");
      })
      .catch((error: Error) => setMessage(error.message));
  }, [googleConnectionId]);

  async function syncData() {
    setSyncing(true);
    try {
      await apiRequest(`/projects/${projectId}/sync-search-console`, {
        method: "POST",
      });
      await loadData();
      setMessage("Search Console-data is bijgewerkt.");
    } catch (error) {
      setMessage((error as Error).message);
    } finally {
      setSyncing(false);
    }
  }

  async function startGoogleConnection() {
    sessionStorage.setItem(returnRouteStorageKey, "search-console");
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
    const property = properties.find((item) => item.siteUrl === selectedProperty);
    if (!googleConnectionId || !property) return;
    try {
      await apiRequest(`/projects/${projectId}/connect-search-console`, {
        body: JSON.stringify({
          google_connection_id: googleConnectionId,
          permission_level: property.permissionLevel,
          property_uri: property.siteUrl,
        }),
        method: "POST",
      });
      sessionStorage.removeItem(connectionStorageKey);
      setGoogleConnectionId("");
      setMessage("Search Console-property is gekoppeld.");
      await syncData();
    } catch (error) {
      setMessage((error as Error).message);
    }
  }

  const metrics = useMemo(() => {
    const clicks = data.pages.reduce((total, row) => total + row.clicks, 0);
    const impressions = data.pages.reduce(
      (total, row) => total + row.impressions,
      0,
    );
    const weightedPosition = data.pages.reduce(
      (total, row) => total + row.average_position * row.impressions,
      0,
    );
    const averagePosition = impressions ? weightedPosition / impressions : 0;
    return [
      { label: "Clicks", value: numberFormatter.format(clicks) },
      { label: "Impressies", value: numberFormatter.format(impressions) },
      { label: "CTR", value: percentFormatter.format(clicks / impressions || 0) },
      {
        label: "Gem. positie",
        value: averagePosition ? decimalFormatter.format(averagePosition) : "0",
      },
    ];
  }, [data.pages]);

  return (
    <section className="data-page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Google-data</p>
          <h1>Search Console</h1>
          <p className="subtitle">
            Zoekprestaties, CTR-kansen en posities per pagina en query.
          </p>
        </div>
        <button
          className="sync-button"
          disabled={syncing}
          onClick={syncData}
          type="button"
        >
          <TrendingUp size={16} />
          {syncing ? "Synchroniseren..." : "Data synchroniseren"}
        </button>
      </div>

      {message && <p className="inline-status">{message}</p>}

      <section className="integration-panel">
        <div>
          <p className="eyebrow">Google koppeling</p>
          <h2>Search Console property</h2>
          <p>
            Koppel een property om echte clicks, impressies, CTR en posities te
            importeren.
          </p>
        </div>
        {properties.length > 0 ? (
          <div className="integration-actions">
            <label>
              Search Console property
              <select
                aria-label="Search Console property"
                value={selectedProperty}
                onChange={(event) => setSelectedProperty(event.target.value)}
              >
                {properties.map((property) => (
                  <option value={property.siteUrl} key={property.siteUrl}>
                    {property.siteUrl}
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
        <section className="search-trend">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Ingeladen pagina's</p>
              <h2>Clicks en impressies</h2>
            </div>
            <MousePointerClick size={19} />
          </div>
          <div className="query-table">
            <div className="query-row header">
              <span>Pagina</span>
              <span>Clicks</span>
              <span>Impressies</span>
              <span>Positie</span>
            </div>
            {data.pages.length === 0 && !loading ? (
              <p className="empty-state">
                Nog geen Search Console-data. Koppel Google en synchroniseer.
              </p>
            ) : (
              data.pages.slice(0, 6).map((page) => (
                <button className="query-row" type="button" key={page.page_url}>
                  <strong>{page.page_url}</strong>
                  <span>{numberFormatter.format(page.clicks)}</span>
                  <span>{numberFormatter.format(page.impressions)}</span>
                  <span>{decimalFormatter.format(page.average_position)}</span>
                </button>
              ))
            )}
          </div>
        </section>

        <section className="query-panel">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Zoekwoorden</p>
              <h2>Topqueries</h2>
            </div>
            <Search size={18} />
          </div>
          <div className="query-table">
            <div className="query-row header">
              <span>Query</span>
              <span>Impressies</span>
              <span>CTR</span>
              <span>Positie</span>
            </div>
            {data.queries.length === 0 && !loading ? (
              <p className="empty-state">Nog geen querydata beschikbaar.</p>
            ) : (
              data.queries.slice(0, 8).map((row) => (
                <button className="query-row" type="button" key={row.query}>
                  <strong>{row.query}</strong>
                  <span>{numberFormatter.format(row.impressions)}</span>
                  <span>{percentFormatter.format(row.ctr)}</span>
                  <span>
                    {decimalFormatter.format(row.average_position)}{" "}
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
