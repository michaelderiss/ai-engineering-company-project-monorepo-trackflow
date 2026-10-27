"use client";

import { FormEvent, useEffect, useState } from "react";
import { API_BASE } from "../../lib/auth";

export default function ResetPasswordPage() {
  const [token, setToken] = useState("");
  const [ready, setReady] = useState(false);
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setToken(new URLSearchParams(window.location.search).get("token") ?? "");
    setReady(true);
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    if (password !== confirmation) {
      setError("The passwords do not match.");
      return;
    }

    setLoading(true);
    try {
      const response = await fetch(`${API_BASE}/auth/reset-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, new_password: password }),
        cache: "no-store",
      });
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(
          typeof body?.detail === "string"
            ? body.detail
            : "This reset link is invalid or expired.",
        );
      }
      window.location.href = "/login?passwordReset=success";
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not reset the password.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main>
      <h1>Choose a new password</h1>
      {!ready ? null : !token ? (
        <section className="panel">
          <p className="error">This reset link is missing or invalid.</p>
          <a href="/forgot-password" className="text-link">Request another link</a>
        </section>
      ) : (
        <section className="panel">
          <form className="stack" onSubmit={handleSubmit}>
            <label>
              New password
              <input
                className="text-input"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                autoComplete="new-password"
                minLength={8}
                required
              />
            </label>
            <label>
              Confirm new password
              <input
                className="text-input"
                type="password"
                value={confirmation}
                onChange={(event) => setConfirmation(event.target.value)}
                autoComplete="new-password"
                minLength={8}
                required
              />
            </label>
            {error && (
              <div>
                <p className="error">{error}</p>
                <a href="/forgot-password" className="text-link">Request a new reset link</a>
              </div>
            )}
            <div className="actions">
              <button type="submit" disabled={loading}>
                {loading ? "Updating..." : "Set new password"}
              </button>
            </div>
          </form>
        </section>
      )}
    </main>
  );
}