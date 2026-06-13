import { KeyRound, LockKeyhole, Mail } from "lucide-react";
import { useState } from "react";

import { defaultBrand } from "../../config/brand";
import { supabase } from "../../lib/supabase";

export function AuthPage() {
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");

  async function signInWithSso(provider: "google" | "azure") {
    if (!supabase) {
      setMessage("SSO is nog niet geconfigureerd.");
      return;
    }
    const { error } = await supabase.auth.signInWithOAuth({
      provider,
      options: {
        redirectTo: `${window.location.origin}/`,
        scopes: provider === "azure" ? "email openid profile" : undefined,
      },
    });
    if (error) setMessage(error.message);
  }

  async function sendMagicLink(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!supabase) {
      setMessage("Login is nog niet geconfigureerd.");
      return;
    }
    const { error } = await supabase.auth.signInWithOtp({
      email,
      options: {
        emailRedirectTo: `${window.location.origin}/`,
      },
    });
    setMessage(
      error?.message ?? "Controleer je e-mail voor de beveiligde inloglink.",
    );
  }

  return (
    <main className="auth-layout">
      <section className="auth-brand">
        <span className="auth-logo">{defaultBrand.name.charAt(0)}</span>
        <p className="eyebrow">{defaultBrand.name}</p>
        <h1>Van SEO-data naar uitvoerbaar werk.</h1>
        <p>
          Eén beveiligde omgeving voor WordPress, Google-data, crawls en
          gecontroleerde publicaties.
        </p>
        <div className="auth-security">
          <LockKeyhole size={17} />
          OAuth 2.0 · versleutelde providersleutels · sessies met automatische
          vernieuwing
        </div>
      </section>
      <section className="auth-form">
        <p className="eyebrow">SSO login</p>
        <h2>Veilig inloggen</h2>
        <p className="auth-intro">
          Gebruik je zakelijke Google- of Microsoft-account. Er wordt geen
          wachtwoord door WP FixPilot opgeslagen.
        </p>
        <button
          className="sso-button"
          onClick={() => signInWithSso("google")}
          type="button"
        >
          <KeyRound size={17} />
          Doorgaan met Google
        </button>
        <button
          className="sso-button"
          onClick={() => signInWithSso("azure")}
          type="button"
        >
          <KeyRound size={17} />
          Doorgaan met Microsoft
        </button>
        <div className="auth-divider"><span>of via beveiligde e-maillink</span></div>
        <form onSubmit={sendMagicLink}>
          <label>
            Zakelijk e-mailadres
            <span className="auth-email-field">
              <Mail size={16} />
              <input
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(event) => setEmail(event.target.value)}
              />
            </span>
          </label>
          <button className="auth-submit" type="submit">
            Stuur inloglink
          </button>
        </form>
        {message && <p className="auth-message">{message}</p>}
      </section>
    </main>
  );
}
