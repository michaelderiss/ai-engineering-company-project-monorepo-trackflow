"use client";

import { useEffect } from "react";
import { getToken } from "../lib/auth";

/**
 * Client-side route guard that checks for a valid auth token in localStorage.
 * If no token is found, the user is redirected to /login.
 *
 * Wrap any protected page content with this component.
 */
export function AuthGuard({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    const token = getToken();
    if (!token) {
      window.location.href = "/login";
    }
  }, []);

  return <>{children}</>;
}