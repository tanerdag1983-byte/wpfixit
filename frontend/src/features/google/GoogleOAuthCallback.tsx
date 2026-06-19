import { useEffect, useState } from "react";

import { apiRequest } from "../../lib/api";

type GoogleCallbackResponse = {
  google_connection_id: string;
  project_id: string;
};

const connectionStorageKey = "wpfixpilot.googleConnectionId";
const returnRouteStorageKey = "wpfixpilot.googleReturnRoute";

export function GoogleOAuthCallback() {
  const [message, setMessage] = useState("Google-koppeling afronden...");

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const code = params.get("code");
    const state = params.get("state");
    if (!code || !state) {
      setMessage("Google gaf geen geldige autorisatie terug.");
      return;
    }

    apiRequest<GoogleCallbackResponse>("/auth/google/callback", {
      body: JSON.stringify({ code, state }),
      method: "POST",
    })
      .then((response) => {
        sessionStorage.setItem(
          connectionStorageKey,
          response.google_connection_id,
        );
        const returnRoute =
          sessionStorage.getItem(returnRouteStorageKey) ?? "search-console";
        window.history.replaceState(null, "", `/#${returnRoute}`);
        window.dispatchEvent(new HashChangeEvent("hashchange"));
        setMessage("Google is gekoppeld. Kies nu je property.");
      })
      .catch((error: Error) => {
        setMessage(error.message);
      });
  }, []);

  return (
    <main className="auth-loading">
      <span className="status-dot" />
      {message}
    </main>
  );
}
