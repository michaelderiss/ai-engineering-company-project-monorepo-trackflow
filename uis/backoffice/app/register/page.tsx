"use client";

import { FormEvent, useState } from "react";
import { publicApiFetch, isObject, RequestError, setToken, redirectToHome } from "../../lib/auth";

type FieldErrors = {
  email?: string;
  password?: string;
  display_name?: string;
  phone?: string;
  address?: string;
};

export default function RegisterPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [phone, setPhone] = useState("");
  const [address, setAddress] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [accountCreated, setAccountCreated] = useState(false);

  async function handleRegister(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (accountCreated) return;
    setLoading(true);
    setError(null);
    setFieldErrors({});

    try {
      // Build the UserCreate payload with optional profile fields
      const profileFields: Record<string, string> = {};

      // display_name is required in ProfileCreate, so use a fallback
      if (displayName.trim()) {
        profileFields.display_name = displayName.trim();
      } else if (phone.trim() || address.trim()) {
        // If other profile fields are filled, use email as display_name
        profileFields.display_name = email.trim().split("@")[0];
      }

      if (phone.trim()) {
        profileFields.phone = phone.trim();
      }
      if (address.trim()) {
        profileFields.address = address.trim();
      }

      const payload: Record<string, unknown> = {
        email: email.trim(),
        password,
      };

      if (Object.keys(profileFields).length > 0) {
        payload.profile = profileFields;
      }

      // Step 1: Create the user (POST /users) — this endpoint is public
      await publicApiFetch("/users", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        cache: "no-store",
      });

      setAccountCreated(true);

      // Step 2: Login with the same credentials to get the token
      const loginBody = new URLSearchParams();
      loginBody.set("username", email.trim());
      loginBody.set("password", password);

      const loginData = await publicApiFetch<{ access_token: string }>("/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: loginBody.toString(),
        cache: "no-store",
      }, (value) => isObject(value) && typeof value.access_token === "string" && value.access_token.length > 0);
      setToken(loginData.access_token);
      redirectToHome();
    } catch (err) {
      if (err instanceof RequestError) setFieldErrors(err.fields);
      const message = err instanceof Error ? err.message : "Unexpected error.";
      setError(message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main>
      <h1>Create an Account</h1>
      <p>Register to access the TrackFlow backoffice applications.</p>

      <section className="panel">
        <form className="stack" onSubmit={handleRegister}>
          <div className="form-grid">
            <label>
              Email <span className="required">*</span>
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
              Password <span className="required">*</span>
              <input
                className="text-input"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={8}
                autoComplete="new-password"
              />
            </label>
            {fieldErrors.password && <p className="error">{fieldErrors.password}</p>}

            <label>
              Display Name
              <input
                className="text-input"
                type="text"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                autoComplete="name"
              />
            </label>
            {fieldErrors.display_name && <p className="error">{fieldErrors.display_name}</p>}

            <label>
              Phone
              <input
                className="text-input"
                type="tel"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                autoComplete="tel"
              />
            </label>

            <label>
              Address
              <input
                className="text-input"
                type="text"
                value={address}
                onChange={(e) => setAddress(e.target.value)}
                autoComplete="street-address"
              />
            </label>
          </div>

          {error && <p className="error">{error}</p>}

          <div className="actions">
            <button type="submit" disabled={loading || accountCreated}>
              {loading ? "Creating account..." : "Create account"}
            </button>
          </div>
        </form>

        {accountCreated && <p className="success">Your account was created. <a href="/login" className="text-link">Continue to sign in</a>.</p>}

        <p>
          Already have an account?{" "}
          <a href="/login" className="text-link">
            Sign in
          </a>
        </p>
      </section>
    </main>
  );
}