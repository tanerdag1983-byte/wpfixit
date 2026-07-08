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
  return "https://wp-fixpilot-api.onrender.com";
}

const apiBaseUrl = resolveApiBaseUrl(
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
