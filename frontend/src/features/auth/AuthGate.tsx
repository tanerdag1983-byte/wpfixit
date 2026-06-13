import { useEffect, useState, type ReactNode } from "react";
import type { Session } from "@supabase/supabase-js";

import { supabase } from "../../lib/supabase";
import { AuthPage } from "./AuthPage";

export function AuthGate({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(Boolean(supabase));
  const loginPreview = window.location.hash === "#login";

  useEffect(() => {
    if (!supabase) return;
    let active = true;
    supabase.auth.getSession().then(({ data }) => {
      if (active) {
        setSession(data.session);
        setLoading(false);
      }
    });
    const { data } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      setSession(nextSession);
      setLoading(false);
    });
    return () => {
      active = false;
      data.subscription.unsubscribe();
    };
  }, []);

  if (loginPreview) return <AuthPage />;
  if (!supabase) return children;
  if (loading) {
    return (
      <main className="auth-loading">
        <span className="status-dot" />
        Beveiligde sessie controleren...
      </main>
    );
  }
  return session ? children : <AuthPage />;
}
