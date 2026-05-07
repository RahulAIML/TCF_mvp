"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { getAuthToken, setAuthToken, clearAuthToken, isTokenExpired } from "@/lib/auth";
import { onAuthFailure, offAuthFailure } from "@/lib/auth-events";

interface AuthUser {
  id: number;
  email: string;
  name?: string | null;
  created_at?: string;
}

interface AuthContextValue {
  user: AuthUser | null;
  token: string | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (token: string, user: AuthUser) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue>({
  user: null,
  token: null,
  isLoading: true,
  isAuthenticated: false,
  login: () => {},
  logout: () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const clearSession = useCallback(() => {
    clearAuthToken();
    if (typeof window !== "undefined") {
      window.localStorage.removeItem("tcf_user");
    }
    setToken(null);
    setUser(null);
  }, []);

  // Rehydrate from localStorage on mount — runs once, before any route guard fires.
  useEffect(() => {
    const storedToken = getAuthToken();
    const storedUser =
      typeof window !== "undefined" ? window.localStorage.getItem("tcf_user") : null;

    if (storedToken && storedUser) {
      if (isTokenExpired(storedToken)) {
        // Token is expired — wipe everything so the middleware redirect happens cleanly.
        clearSession();
      } else {
        try {
          // Re-sync the cookie using the JWT's own expiry.
          // This is the key fix: cookie stays alive as long as the token is valid,
          // even if the user never calls setAuthToken again (e.g. revisits days later).
          setAuthToken(storedToken);
          setToken(storedToken);
          setUser(JSON.parse(storedUser) as AuthUser);
        } catch {
          clearSession();
        }
      }
    }

    setIsLoading(false);
  }, [clearSession]);

  // Automatically log out when any API call receives a 401.
  useEffect(() => {
    onAuthFailure(clearSession);
    return () => offAuthFailure(clearSession);
  }, [clearSession]);

  const login = useCallback((newToken: string, newUser: AuthUser) => {
    setAuthToken(newToken);
    if (typeof window !== "undefined") {
      window.localStorage.setItem("tcf_user", JSON.stringify(newUser));
    }
    setToken(newToken);
    setUser(newUser);
  }, []);

  const logout = useCallback(() => {
    clearSession();
  }, [clearSession]);

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        isLoading,
        isAuthenticated: !isLoading && user !== null,
        login,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
