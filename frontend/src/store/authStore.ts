






import { create } from "zustand";
import { loginApi, registerApi, logoutApi, getMeApi } from "../api/auth";
import { setTokens, clearTokens, getAccessToken, getRefreshToken } from "../api/client";
import type { User, LoginRequest, RegisterRequest } from "../types";

interface AuthState {
  user: User | null;
  accessToken: string | null;
  refreshToken: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;

  login: (data: LoginRequest) => Promise<void>;
  register: (data: RegisterRequest) => Promise<void>;
  logout: () => Promise<void>;
  hydrate: () => Promise<void>;
  setTokensFromOAuth: (accessToken: string, refreshToken: string) => void;
  clearError: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  accessToken: getAccessToken(),
  refreshToken: getRefreshToken(),
  isAuthenticated: !!getAccessToken(),
  isLoading: false,
  error: null,

  login: async (data: LoginRequest) => {
    set({ isLoading: true, error: null });
    try {
      const resp = await loginApi(data);
      setTokens(resp.access_token, resp.refresh_token);
      const user = await getMeApi();
      set({
        user,
        accessToken: resp.access_token,
        refreshToken: resp.refresh_token,
        isAuthenticated: true,
        isLoading: false,
      });
    } catch (err: unknown) {
      const message = extractErrorMessage(err, "Login failed");
      set({ isLoading: false, error: message });
      throw err;
    }
  },

  register: async (data: RegisterRequest) => {
    set({ isLoading: true, error: null });
    try {
      const resp = await registerApi(data);
      setTokens(resp.access_token, resp.refresh_token);
      const user = await getMeApi();
      set({
        user,
        accessToken: resp.access_token,
        refreshToken: resp.refresh_token,
        isAuthenticated: true,
        isLoading: false,
      });
    } catch (err: unknown) {
      const message = extractErrorMessage(err, "Registration failed");
      set({ isLoading: false, error: message });
      throw err;
    }
  },

  logout: async () => {
    try {
      await logoutApi();
    } catch {
      
    }
    clearTokens();
    set({
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
      error: null,
    });
  },

  hydrate: async () => {
    const token = getAccessToken();
    if (!token) {
      set({ isAuthenticated: false, isLoading: false });
      return;
    }
    set({ isLoading: true });
    try {
      const user = await getMeApi();
      set({ user, isAuthenticated: true, isLoading: false });
    } catch {
      clearTokens();
      set({
        user: null,
        accessToken: null,
        refreshToken: null,
        isAuthenticated: false,
        isLoading: false,
      });
    }
  },

  setTokensFromOAuth: (accessToken: string, refreshToken: string) => {
    setTokens(accessToken, refreshToken);
    set({ accessToken, refreshToken, isAuthenticated: true });
  },

  clearError: () => set({ error: null }),
}));

import { extractErrorMessage } from "../utils/errors";
