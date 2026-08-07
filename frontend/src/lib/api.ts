import { supabase } from "./supabase";

export function resolveApiBaseUrl(
  configuredBaseUrl?: string,
  hostname?: string,
) {
  if (configuredBaseUrl) return configuredBaseUrl;
  if (
    hostname === "localhost" ||
    hostname === "127.0.0.1" ||
    hostname === "::1"
  ) {
    return "http://localhost:8000";
  }
  return "/api";
}

export const apiBaseUrl = resolveApiBaseUrl(
  import.meta.env.VITE_API_BASE_URL as string | undefined,
  window.location.hostname,
);
const developmentAccessToken = import.meta.env.VITE_DEV_ACCESS_TOKEN as
  | string
  | undefined;

export function resolveAccessToken(
  sessionToken?: string,
  developmentToken?: string,
) {
  return sessionToken || developmentToken;
}

export async function apiRequest<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const session = supabase
    ? (await supabase.auth.getSession()).data.session
    : null;
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  const accessToken = resolveAccessToken(
    session?.access_token,
    developmentAccessToken,
  );
  if (accessToken) {
    headers.set("Authorization", `Bearer ${accessToken}`);
  }

  const response = await fetch(`${apiBaseUrl}${path}`, {
    ...init,
    headers,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(formatApiError(body));
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

function formatApiError(body: unknown) {
  if (!body || typeof body !== "object") return "De aanvraag is mislukt";
  if (!("detail" in body)) return "De aanvraag is mislukt";

  return formatDetail((body as { detail: unknown }).detail);
}

function formatDetail(detail: unknown): string {
  if (typeof detail === "string" && detail.trim()) return detail.trim();
  if (Array.isArray(detail)) {
    const messages = detail.map(formatValidationItem).filter(Boolean);
    return messages.length ? messages.join("; ") : "De aanvraag is mislukt";
  }
  if (detail && typeof detail === "object") {
    const message =
      (detail as { msg?: unknown; message?: unknown }).msg ??
      (detail as { message?: unknown }).message;
    if (typeof message === "string" && message.trim()) return message.trim();
  }
  return "De aanvraag is mislukt";
}

function formatValidationItem(item: unknown): string {
  if (!item || typeof item !== "object") return "";
  const payload = item as { loc?: unknown; msg?: unknown; message?: unknown };
  const message = payload.msg ?? payload.message;
  if (typeof message !== "string" || !message.trim()) return "";
  const location = Array.isArray(payload.loc)
    ? payload.loc
        .filter((part) => typeof part === "string" || typeof part === "number")
        .filter((part) => part !== "body")
        .join(".")
    : "";
  return location ? `${location}: ${message}` : message;
}

export type ScoreFactor = {
  key: string;
  value: unknown;
  points: number;
  max_points: number;
  explanation: string;
  suggested_action: string;
  evidence: Record<string, unknown>;
};

export type ScoreSnapshot = {
  overall_score: number;
  factors: ScoreFactor[];
};

export type PageVersion = {
  id: string;
  content_hash: string;
  source?: string;
  snapshot_payload?: Record<string, unknown>;
  proposal_version_id?: string | null;
  draft_job_id?: string | null;
  observed_at?: string;
  published_at?: string | null;
};

export type PageRecommendation = {
  id: string;
  page_version_id: string;
  state: string;
  evidence: Record<string, unknown>;
  suggested_action: string;
  created_at: string;
};

export type StoredScoreSnapshot = ScoreSnapshot & {
  id: string;
  page_version_id: string;
  created_at: string;
};

export type PageTimelineEvent = {
  id: string;
  event_type: string;
  payload: Record<string, unknown>;
  created_at: string;
  page_version_id?: string | null;
};

export type PageMonitoring = {
  page: {
    id: string;
    title?: string;
    url?: string;
    wordpress_status?: string;
    status: string;
  };
  latest_sync_at: string | null;
  next_check_at: string | null;
  captured_version: PageVersion | null;
  captured_score: StoredScoreSnapshot | null;
  live_changed_since_capture: boolean;
  versions: PageVersion[];
  scores: StoredScoreSnapshot[];
  projected_score: ScoreSnapshot | null;
  recommendations: PageRecommendation[];
  events: PageTimelineEvent[];
};
