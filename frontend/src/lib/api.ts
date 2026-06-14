import { supabase } from "./supabase";

const apiBaseUrl =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ??
  "http://localhost:8000";
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
    const body = (await response.json().catch(() => null)) as {
      detail?: string;
    } | null;
    throw new Error(body?.detail ?? "De aanvraag is mislukt");
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}
