import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type PropsWithChildren,
} from "react";

import { apiRequest, ApiError } from "../../api/http";
import type { Admin, AuthResponse, SetupStatusResponse } from "../../lib/types";

interface AuthContextValue {
  token: string | null;
  admin: Admin | null;
  isReady: boolean;
  isInitialized: boolean | null;
  login: (username: string, password: string) => Promise<void>;
  completeSetup: (username: string, password: string, passwordConfirm: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

const TOKEN_KEY = "workspace-session-token";

export function AuthProvider({ children }: PropsWithChildren) {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(TOKEN_KEY));
  const [admin, setAdmin] = useState<Admin | null>(null);
  const [isReady, setIsReady] = useState(false);
  const [isInitialized, setIsInitialized] = useState<boolean | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function syncAuthState() {
      setIsReady(false);
      try {
        const setup = await apiRequest<SetupStatusResponse>("/auth/setup-status");
        if (cancelled) {
          return;
        }
        setIsInitialized(setup.is_initialized);

        if (!setup.is_initialized) {
          localStorage.removeItem(TOKEN_KEY);
          setToken(null);
          setAdmin(null);
          setIsReady(true);
          return;
        }

        if (!token) {
          setAdmin(null);
          setIsReady(true);
          return;
        }

        const payload = await apiRequest<Admin>("/auth/me", { method: "GET" }, token);
        if (cancelled) {
          return;
        }
        setAdmin(payload);
        setIsReady(true);
      } catch (error) {
        if (cancelled) {
          return;
        }
        if (error instanceof ApiError && error.status === 409) {
          setIsInitialized(false);
        } else {
          setIsInitialized((current) => current ?? true);
        }
        localStorage.removeItem(TOKEN_KEY);
        setToken(null);
        setAdmin(null);
        setIsReady(true);
      }
    }

    void syncAuthState();
    return () => {
      cancelled = true;
    };
  }, [token]);

  const value = useMemo<AuthContextValue>(
    () => ({
      token,
      admin,
      isReady,
      isInitialized,
      async login(username: string, password: string) {
        const payload = await apiRequest<AuthResponse>("/auth/login", {
          method: "POST",
          body: JSON.stringify({ username, password })
        });
        setIsInitialized(true);
        localStorage.setItem(TOKEN_KEY, payload.access_token);
        setToken(payload.access_token);
        setAdmin(payload.admin);
      },
      async completeSetup(username: string, password: string, passwordConfirm: string) {
        const payload = await apiRequest<AuthResponse>("/auth/setup", {
          method: "POST",
          body: JSON.stringify({
            username,
            password,
            password_confirm: passwordConfirm
          })
        });
        setIsInitialized(true);
        localStorage.setItem(TOKEN_KEY, payload.access_token);
        setToken(payload.access_token);
        setAdmin(payload.admin);
      },
      logout() {
        localStorage.removeItem(TOKEN_KEY);
        setToken(null);
        setAdmin(null);
      }
    }),
    [admin, isInitialized, isReady, token]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new ApiError("AuthContext не инициализирован", 500);
  }
  return context;
}
