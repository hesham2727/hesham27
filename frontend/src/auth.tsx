import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, setUnauthorizedHandler, type User } from "./api";
import { useI18n } from "./i18n";

interface AuthState { user: User | null; loading: boolean; needsSetup: boolean; login: (u: string, p: string) => Promise<void>; logout: () => Promise<void>; refresh: () => Promise<void>; setup: (u: string, p: string, fullName: string) => Promise<void> }
const Ctx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [needsSetup, setNeedsSetup] = useState(false);
  const { setLang } = useI18n();

  const refresh = useCallback(async () => {
    try {
      const s = await api<{ needs_setup: boolean }>("/api/auth/setup-status");
      setNeedsSetup(s.needs_setup);
      if (s.needs_setup) {
        setUser(null);
        return;
      }
      setUser(await api<User>("/api/auth/me"));
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(() => setUser(null));
    void refresh();
    return () => setUnauthorizedHandler(null);
  }, [refresh]);

  const login = useCallback(async (username: string, password: string) => {
    const r = await api<{ user: User }>("/api/auth/login", { method: "POST", body: { username, password, client: "web" } });
    setUser(r.user);
    setLang(r.user.language);
  }, [setLang]);

  const logout = useCallback(async () => {
    try {
      await api("/api/auth/logout", { method: "POST" });
    } finally {
      setUser(null);
    }
  }, []);

  const setup = useCallback(async (username: string, password: string, full_name: string) => {
    await api("/api/auth/setup", { method: "POST", body: { username, password, full_name } });
    setNeedsSetup(false);
    await login(username, password);
  }, [login]);

  return <Ctx.Provider value={{ user, loading, needsSetup, login, logout, refresh, setup }}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthState {
  const v = useContext(Ctx);
  if (!v) throw new Error("AuthProvider missing");
  return v;
}
