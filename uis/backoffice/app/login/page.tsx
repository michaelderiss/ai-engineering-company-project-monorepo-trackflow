"use client";

import { FormEvent, useEffect, useState } from "react";
import { publicApiFetch, isObject, setToken, redirectToHome } from "../../lib/auth";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [resetNotice, setResetNotice] = useState(false);

  useEffect(() => {
    setResetNotice(new URLSearchParams(window.location.search).get("passwordReset") === "success");
  }, []);

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    setFieldErrors({});

    try {
      // The /auth/login endpoint uses OAuth2PasswordRequestForm
      // which expects form-data with username and password fields.
      const body = new URLSearchParams();
      body.set("username", email);
      body.set("password", password);

      const data = await publicApiFetch<{ access_token: string }>(
        "/auth/login",
        {
          method: "POST",
          headers: { "Content-Type": "application/x-www-form-urlencoded" },
          body: body.toString(),
          cache: "no-store",
        }, (value) => isObject(value) && typeof value.access_token === "string" && value.access_token.length > 0,
      );
      setToken(data.access_token);
      redirectToHome();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unexpected error.";
      setError(message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main>
      <h1>Sign in to TrackFlow</h1>
      <p>Enter your credentials to access the backoffice.</p>
      {resetNotice && <p className="success">Your password has been reset. Sign in with your new password.</p>}

      <section className="panel">
        <form className="stack" onSubmit={handleLogin}>
          <div className="form-grid">
            <label>
              Email
              <input
                className="text-input"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoComplete="email"
              />
            </label>
            {fieldErrors.email && <p className="error">{fieldErrors.email}</p>}

            <label>
              Password
              <input
                className="text-input"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                autoComplete="current-password"
              />
            </label>
            {fieldErrors.password && <p className="error">{fieldErrors.password}</p>}
          </div>

          <a href="/forgot-password" className="text-link">Forgot your password?</a>

          {error && <p className="error">{error}</p>}

          <div className="actions">
            <button type="submit" disabled={loading}>
              {loading ? "Signing in..." : "Sign in"}
            </button>
          </div>
        </form>

        <p>
          Don&apos;t have an account?{" "}
          <a href="/register" className="text-link">
            Register here
          </a>
        </p>
      </section>
    </main>
  );
}