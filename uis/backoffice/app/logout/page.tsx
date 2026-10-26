"use client";

import { useEffect } from "react";
import { clearToken, redirectToLogin } from "../../lib/auth";

export default function LogoutPage() {
  useEffect(() => {
    clearToken();
    redirectToLogin();
  }, []);

  // Fallback in case JavaScript redirect fails
  return (
    <main>
      <h1>Logged Out</h1>
      <section className="panel">
        <p>You have been signed out successfully.</p>
        <a href="/login" className="launcher-link">Sign in again</a>
      </section>
    </main>
  );
}