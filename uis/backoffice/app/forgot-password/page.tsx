"use client";

import { FormEvent, useState } from "react";
import { publicApiFetch } from "../../lib/auth";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError(null);

    try {
      await publicApiFetch("/auth/forgot-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim() }),
        cache: "no-store",
      });
      setSubmitted(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not submit the request.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main>
      <h1>Reset your password</h1>
      {submitted ? (
        <section className="panel">
          <p className="success">If that address is registered, you&apos;ll receive a password reset link.</p>
          <a href="/login" className="text-link">Back to sign in</a>
        </section>
      ) : (
        <section className="panel">
          <form className="stack" onSubmit={handleSubmit}>
            <label>
              Email
              <input
                className="text-input"
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                autoComplete="email"
                required
              />
            </label>
            {error && <p className="error">{error}</p>}
            <div className="actions">
              <button type="submit" disabled={loading}>
                {loading ? "Sending..." : "Send reset link"}
              </button>
              <a href="/login" className="text-link">Back to sign in</a>
            </div>
          </form>
        </section>
      )}
    </main>
  );
}