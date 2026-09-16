import { ArrowRight, ChartNoAxesCombined, Eye, EyeOff, Fingerprint, Layers3, LoaderCircle, ScanLine } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import { ApiError } from "@/api/client";
import { useLogin, useMe } from "@/hooks/useAuth";
import "./LoginPage.css";

/**
 * The login form is a plain controlled form on purpose (perf). It used to pull
 * react-hook-form + zod + @hookform/resolvers just to enforce "field not empty"
 * — and those three libs were used NOWHERE else in the app, so they weighed down
 * the very first, unauthenticated paint for two required fields. A couple of
 * useState hooks do the same job with none of the weight.
 */
export default function LoginPage() {
  const me = useMe();
  const login = useLogin();
  const navigate = useNavigate();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [attempted, setAttempted] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const usernameRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (me.data) navigate("/", { replace: true });
  }, [me.data, navigate]);

  // Errors only show after a submit attempt (same UX as the old onSubmit mode).
  const usernameError = attempted && !username ? "Inserisci lo username" : null;
  const passwordError = attempted && !password ? "Inserisci la password" : null;

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (login.isPending) return;
    setAttempted(true);
    setFormError(null);
    if (!username || !password) {
      (!username ? usernameRef : passwordRef).current?.focus();
      return;
    }
    try {
      await login.mutateAsync({ username, password });
      navigate("/", { replace: true });
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setFormError("Credenziali non valide. Controlla username e password e riprova.");
      } else if (err instanceof ApiError && err.status === 429) {
        setFormError("Troppi tentativi di accesso. Attendi prima di riprovare.");
      } else {
        setFormError("Accesso non riuscito. Riprova tra poco.");
      }
    }
  };

  return (
    <main className="login-page">
      <div className="login-layout">
        <section className="login-intro" aria-labelledby="login-brand-name">
          <div className="login-brand">
            <img src="/brand/finance-alert-mark.webp" width="80" height="80" alt="" fetchPriority="high" />
            <div>
              <p id="login-brand-name" className="login-brand-name">Finance <span>Alert</span></p>
              <p className="login-brand-caption">Il tuo osservatorio sui mercati</p>
            </div>
          </div>

          <div className="login-story">
            <p className="login-eyebrow"><span aria-hidden="true" /> Osserva. Collega. Approfondisci.</p>
            <h1>Il mercato,<br /><span>messo a fuoco.</span></h1>
            <p className="login-description">Titoli, setup e segnali in un unico spazio.<br className="login-desktop-break" /> Per leggere i movimenti con il loro contesto.</p>
            <ul className="login-features">
              <li><ScanLine aria-hidden="true" /><div><h2>Segui ciò che si forma</h2><p>Dai setup ai segnali, senza perdere il filo.</p></div></li>
              <li><Layers3 aria-hidden="true" /><div><h2>Collega le informazioni</h2><p>Prezzi, fondamentali ed eventi, titolo per titolo.</p></div></li>
              <li><ChartNoAxesCombined aria-hidden="true" /><div><h2>Rileggi gli esiti</h2><p>Uno storico misurabile, con i suoi limiti.</p></div></li>
            </ul>
          </div>
          <p className="login-intro-footer">Meno rumore. Più contesto.</p>
        </section>

        <section className="login-access" aria-labelledby="login-title">
          <div className="login-card">
            <div className="login-access-label"><Fingerprint aria-hidden="true" /> Area personale</div>
            <h2 id="login-title">Bentornato.</h2>
            <p className="login-card-description">Accedi al tuo spazio di analisi.</p>
            <form className="login-form" onSubmit={onSubmit} noValidate aria-busy={login.isPending}>
              <div className="login-field">
                <label htmlFor="username">Username</label>
                <input
                  id="username"
                  name="username"
                  ref={usernameRef}
                  autoComplete="username"
                  autoCapitalize="none"
                  spellCheck={false}
                  placeholder="Il tuo username"
                  required
                  disabled={login.isPending}
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  aria-invalid={!!usernameError}
                  aria-describedby={usernameError ? "login-username-error" : undefined}
                />
                {usernameError && <p id="login-username-error" className="login-field-error">{usernameError}</p>}
              </div>
              <div className="login-field">
                <label htmlFor="password">Password</label>
                <div className="login-password">
                  <input
                    id="password"
                    name="password"
                    ref={passwordRef}
                    type={showPassword ? "text" : "password"}
                    autoComplete="current-password"
                    placeholder="La tua password"
                    required
                    disabled={login.isPending}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    aria-invalid={!!passwordError}
                    aria-describedby={passwordError ? "login-password-error" : undefined}
                  />
                  <button type="button" className="login-password-toggle" onClick={() => setShowPassword((v) => !v)} aria-label={showPassword ? "Nascondi password" : "Mostra password"} aria-controls="password" aria-pressed={showPassword}>
                    {showPassword ? <EyeOff aria-hidden="true" /> : <Eye aria-hidden="true" />}
                  </button>
                </div>
                {passwordError && <p id="login-password-error" className="login-field-error">{passwordError}</p>}
              </div>
              {formError && <p className="login-form-error" role="alert">{formError}</p>}
              <button className="login-submit" type="submit" disabled={login.isPending}>
                {login.isPending ? <>Accesso in corso… <LoaderCircle className="motion-safe:animate-spin" aria-hidden="true" /></> : <>Accedi <ArrowRight aria-hidden="true" /></>}
              </button>
            </form>
            <p className="login-form-note">Usa le credenziali del tuo account.</p>
          </div>
          <p className="login-access-footer">Il tuo punto di partenza per leggere il mercato.</p>
        </section>
      </div>
    </main>
  );
}
