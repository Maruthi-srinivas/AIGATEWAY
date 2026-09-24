import { useState } from "react";

import { ApiError, login, loginWithApiKey } from "../api/client";
import { DEMO_API_KEY, DEMO_PASSWORD, SEEDED_USERS, useSession } from "../api/session";
import { Guide } from "../components/Guide";

export function LoginPanel() {
  const [email, setEmail] = useState<string>(SEEDED_USERS[1].email);
  const [password, setPassword] = useState(DEMO_PASSWORD);
  const [apiKey, setApiKey] = useState(DEMO_API_KEY);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const selected = SEEDED_USERS.find((user) => user.email === email);

  async function onPassword(event: React.FormEvent) {
    event.preventDefault();
    setPending(true);
    setError(null);
    try {
      await login(email, password);
    } catch (err) {
      setError(err instanceof ApiError ? `${err.status} ${err.code}: ${err.detail}` : "Login failed");
    } finally {
      setPending(false);
    }
  }

  async function onKey(event: React.FormEvent) {
    event.preventDefault();
    setPending(true);
    setError(null);
    try {
      await loginWithApiKey(apiKey.trim());
    } catch (err) {
      setError(err instanceof ApiError ? `${err.status} ${err.code}: ${err.detail}` : "API key rejected");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="page">
      <Guide
        screen="Pick a seeded local user, then sign in. The cards show the role, the tenant, and the email. The password is the same for every card."
        first="Click a user card. Confirm the password chip says changeme. Then press Sign in."
      />
      <div className="login-screen">
        <section className="panel">
          <h2>Who are you signing in as?</h2>
          <p className="hint">Each card fills the email field. It does not submit until you press Sign in.</p>
          <div className="user-grid">
            {SEEDED_USERS.map((user) => (
              <button
                key={user.email}
                type="button"
                className="user-card"
                aria-pressed={user.email === email}
                onClick={() => setEmail(user.email)}
              >
                <strong>{user.label}</strong>
                <span>Role {user.role}</span>
                <span>Tenant {user.tenant}</span>
                <span>{user.email}</span>
              </button>
            ))}
          </div>
        </section>
        <section className="panel">
          <h2>Sign in</h2>
          <p className="chip">Local password: {DEMO_PASSWORD}</p>
          <p className="hint">
            {selected
              ? `${selected.label} can ${selected.role === "viewer" ? "read conversations only" : selected.role === "app_user" ? "chat in this tenant" : "chat, and security or platform admins can also ingest and edit policy"}.`
              : "Choose a card first."}
          </p>
          <form onSubmit={(event) => void onPassword(event)} className="stack">
            <label>
              Email
              <span className="hint">Goes to POST /v1/auth/login on the public gateway.</span>
              <input value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="username" />
            </label>
            <label>
              Password
              <span className="hint">Shown on purpose. Local Docker only.</span>
              <input value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" />
            </label>
            <button type="submit" disabled={pending}>
              Sign in as {selected?.label ?? "this user"}
            </button>
          </form>
          <form onSubmit={(event) => void onKey(event)} className="stack">
            <label>
              API key
              <span className="hint">Second way in. The HR demo key is a service account, not a user password.</span>
              <input value={apiKey} onChange={(event) => setApiKey(event.target.value)} spellCheck={false} />
            </label>
            <button type="button" className="secondary" onClick={() => setApiKey(DEMO_API_KEY)}>
              Fill HR demo key
            </button>
            <button type="submit" disabled={pending}>
              Use API key
            </button>
          </form>
          {error ? <p className="error">{error}</p> : null}
        </section>
      </div>
    </div>
  );
}

export function AuthGate({ children }: { children: React.ReactNode }) {
  const session = useSession();
  if (!session.me) {
    return <LoginPanel />;
  }
  return <>{children}</>;
}
