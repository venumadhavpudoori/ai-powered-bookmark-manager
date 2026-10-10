"use client";

import {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
  type ReactNode,
} from "react";
import { useRouter } from "next/navigation";
import {
  login as apiLogin,
  register as apiRegister,
  logout as apiLogout,
  isAuthenticated,
} from "@/lib/api";

interface AuthContextType {
  isLoggedIn: boolean;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (
    email: string,
    password: string,
    displayName?: string
  ) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    setIsLoggedIn(isAuthenticated());
    setLoading(false);
  }, []);

  const login = useCallback(
    async (email: string, password: string) => {
      await apiLogin(email, password);
      setIsLoggedIn(true);
      router.push("/dashboard");
    },
    [router]
  );

  const register = useCallback(
    async (email: string, password: string, displayName?: string) => {
      await apiRegister(email, password, displayName);
      await apiLogin(email, password);
      setIsLoggedIn(true);
      router.push("/dashboard");
    },
    [router]
  );

  const logout = useCallback(() => {
    apiLogout();
    setIsLoggedIn(false);
    router.push("/login");
  }, [router]);

  return (
    <AuthContext.Provider value={{ isLoggedIn, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
