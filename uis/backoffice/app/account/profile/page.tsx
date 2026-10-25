"use client";

import { FormEvent, useEffect, useState } from "react";
import { apiFetch, getToken } from "../../../lib/auth";

type Profile = {
  id: number;
  user_id: number;
  display_name: string;
  phone: string | null;
  address: string | null;
};

type User = {
  id: number;
  email: string;
  is_active: boolean;
  role: string;
  created_at: string;
  updated_at: string;
  profile: Profile | null;
};

export default function ProfilePage() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Profile edit fields
  const [displayName, setDisplayName] = useState("");
  const [phone, setPhone] = useState("");
  const [address, setAddress] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState(false);

  const [profile, setProfile] = useState<Profile | null>(null);

  useEffect(() => {
    let ignore = false;

    async function loadUser() {
      setLoading(true);
      setError(null);

      try {
        const userData = await apiFetch<User>("/auth/me");
        if (ignore) return;
        setUser(userData);

        // Load linked profile data — either from the user object or from /profiles/me
        if (userData.profile) {
          setProfile(userData.profile);
          setDisplayName(userData.profile.display_name);
          setPhone(userData.profile.phone ?? "");
          setAddress(userData.profile.address ?? "");
        } else {
          // Try loading the profile separately
          try {
            const profileData = await apiFetch<Profile>("/profiles/me");
            if (ignore) return;
            setProfile(profileData);
            setDisplayName(profileData.display_name);
            setPhone(profileData.phone ?? "");
            setAddress(profileData.address ?? "");
          } catch {
            // No profile yet — that's fine, the form allows creating one
          }
        }
      } catch (err) {
        if (!ignore) {
          const message = err instanceof Error ? err.message : "Could not load profile.";
          setError(message);
        }
      } finally {
        if (!ignore) {
          setLoading(false);
        }
      }
    }

    loadUser();

    return () => {
      ignore = true;
    };
  }, []);

  async function handleSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    setSaving(true);
    setSaveError(null);
    setSaveSuccess(false);

    try {
      const updated = await apiFetch<Profile>("/profiles/me", {
        method: "PATCH",
        body: JSON.stringify({
          display_name: displayName.trim() || "User",
          phone: phone.trim() || null,
          address: address.trim() || null,
        }),
      });

      setProfile(updated);
      setSaveSuccess(true);

      // Also update the local user profile reference
      if (user) {
        setUser({ ...user, profile: updated });
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "Could not save profile.";
      setSaveError(message);
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <main>
        <h1>My Profile</h1>
        <section className="panel">
          <p>Loading profile...</p>
        </section>
      </main>
    );
  }

  if (error) {
    return (
      <main>
        <h1>My Profile</h1>
        <section className="panel">
          <p className="error">{error}</p>
          <a href="/" className="launcher-link">Back to home</a>
        </section>
      </main>
    );
  }

  return (
    <main>
      <h1>My Profile</h1>

      <section className="panel">
        <h2>Account Information</h2>
        <div className="grid">
          <article className="metric">
            <h4>Email</h4>
            <p>{user?.email ?? "—"}</p>
          </article>
          <article className="metric">
            <h4>Role</h4>
            <p>{user?.role ?? "—"}</p>
          </article>
          <article className="metric">
            <h4>Account Status</h4>
            <p>{user?.is_active === false ? "Inactive" : "Active"}</p>
          </article>
          <article className="metric">
            <h4>Member since</h4>
            <p>{user?.created_at ? new Date(user.created_at).toLocaleDateString() : "—"}</p>
          </article>
        </div>
      </section>

      <section className="panel">
        <h2>Edit Profile</h2>
        <form className="stack" onSubmit={handleSave}>
          <div className="form-grid">
            <label>
              Display Name <span className="required">*</span>
              <input
                className="text-input"
                type="text"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                required
              />
            </label>

            <label>
              Phone
              <input
                className="text-input"
                type="tel"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
              />
            </label>

            <label>
              Address
              <input
                className="text-input"
                type="text"
                value={address}
                onChange={(e) => setAddress(e.target.value)}
              />
            </label>
          </div>

          {saveError && <p className="error">{saveError}</p>}
          {saveSuccess && <p className="success">Profile updated successfully.</p>}

          <div className="actions">
            <button type="submit" disabled={saving}>
              {saving ? "Saving..." : "Save changes"}
            </button>
            <a href="/" className="launcher-link">Back to home</a>
          </div>
        </form>
      </section>
    </main>
  );
}