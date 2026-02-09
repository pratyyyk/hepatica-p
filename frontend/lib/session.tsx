"use client";

import { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { apiFetch } from "@/lib/api";

export interface AuthSession {
  authenticated: boolean;
  user_id: string;
  email: string;
  role: string;
  csrf_token: string | null;
  csrf_header_name: string;
}

interface SessionContextValue {
  loading: boolean;
  session: AuthSession | null;
  csrfToken: string | null;
  csrfHeaderName: string;
  refresh: () => Promise<void>;
  loginDev: (email: string) => Promise<void>;
  logout: () => Promise<void>;
}

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<AuthSession | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const payload = await apiFetch<AuthSession>("/api/v1/auth/session");
      setSession(payload);
    } catch {
      setSession(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const loginDev = useCallback(async (email: string) => {
    await apiFetch("/api/v1/auth/dev-login", {
      method: "POST",
      body: { email },
      csrfToken: session?.csrf_token || null,
      csrfHeaderName: session?.csrf_header_name,
    });
    await refresh();
  }, [refresh, session?.csrf_header_name, session?.csrf_token]);

  const logout = useCallback(async () => {
    await apiFetch("/api/v1/auth/logout", {
      method: "POST",
      body: {},
      csrfToken: session?.csrf_token || null,
      csrfHeaderName: session?.csrf_header_name,
    });
    setSession(null);
  }, [session?.csrf_header_name, session?.csrf_token]);

  const value = useMemo<SessionContextValue>(() => {
    return {
      loading,
      session,
      csrfToken: session?.csrf_token || null,
      csrfHeaderName: session?.csrf_header_name || "x-csrf-token",
      refresh,
      loginDev,
      logout,
    };
  }, [loading, loginDev, logout, refresh, session]);

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession() {
  const value = useContext(SessionContext);
  if (!value) {
    throw new Error("useSession must be used within SessionProvider");
  }
  return value;
}
