"use client";

import { FormEvent, useState } from "react";
import { apiFetch } from "../../../lib/auth";

export default function ChangePasswordPage() {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSuccess(false);
    if (newPassword !== confirmation) {
      setError("The new password and confirmation do not match.");
      return;
    }

    setLoading(true);
    try {
      await apiFetch<{ message: string }>("/auth/change-password", {
        method: "POST",
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: newPassword,
        }),
      });
      setCurrentPassword("");
      setNewPassword("");
      setConfirmation("");
      setSuccess(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not change the password.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main>
      <h1>Change password</h1>
      <section className="panel">
        <form className="stack" onSubmit={handleSubmit}>
          <label>
            Current password
            <input
              className="text-input"
              type="password"
              value={currentPassword}
              onChange={(event) => setCurrentPassword(event.target.value)}
              autoComplete="current-password"
              required
            />
          </label>
          <label>
            New password
            <input
              className="text-input"
              type="password"
              value={newPassword}
              onChange={(event) => setNewPassword(event.target.value)}
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
          {error && <p className="error">{error}</p>}
          {success && <p className="success">Password changed successfully.</p>}
          <div className="actions">
            <button type="submit" disabled={loading}>
              {loading ? "Updating..." : "Change password"}
            </button>
            <a href="/account/profile" className="text-link">Back to profile</a>
          </div>
        </form>
      </section>
    </main>
  );
}