import { useState } from "react";

import { supabase } from "../../lib/supabase";

export function AuthPage() {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!supabase) {
      setMessage("Supabase is nog niet geconfigureerd.");
      return;
    }

    const result =
      mode === "login"
        ? await supabase.auth.signInWithPassword({ email, password })
        : await supabase.auth.signUp({ email, password });
    setMessage(result.error?.message ?? "Controleer je e-mail om door te gaan.");
  }

  return (
    <main className="auth-layout">
      <section className="auth-brand">
        <span className="auth-logo">W</span>
        <p className="eyebrow">WP FixPilot</p>
        <h1>Van SEO-data naar uitvoerbaar werk.</h1>
        <p>
          Combineer WordPress, Google en crawldata zonder tussen losse tools te
          schakelen.
        </p>
      </section>
      <form className="auth-form" onSubmit={submit}>
        <p className="eyebrow">{mode === "login" ? "Welkom terug" : "Start nu"}</p>
        <h2>{mode === "login" ? "Inloggen" : "Account aanmaken"}</h2>
        <label>
          E-mailadres
          <input
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </label>
        <label>
          Wachtwoord
          <input
            type="password"
            autoComplete={mode === "login" ? "current-password" : "new-password"}
            minLength={8}
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>
        <button className="auth-submit" type="submit">
          {mode === "login" ? "Inloggen" : "Registreren"}
        </button>
        <button
          className="auth-mode"
          type="button"
          onClick={() => setMode(mode === "login" ? "register" : "login")}
        >
          {mode === "login"
            ? "Nog geen account? Registreren"
            : "Al een account? Inloggen"}
        </button>
        {message && <p className="auth-message">{message}</p>}
      </form>
    </main>
  );
}

