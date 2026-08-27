





import { create } from "zustand";
import {
  createSessionApi,
  deleteSessionApi,
  listSessionsApi,
  updateSessionApi,
} from "../api/sessions";
import type { Session } from "../types";

interface SessionState {
  sessions: Session[];
  total: number;
  page: number;
  pageSize: number;
  isLoading: boolean;
  error: string | null;

  fetchSessions: (page?: number) => Promise<void>;
  createSession: (name: string) => Promise<Session>;
  renameSession: (id: string, name: string) => Promise<void>;
  deleteSession: (id: string) => Promise<void>;
  clearError: () => void;
}

export const useSessionStore = create<SessionState>((set, get) => ({
  sessions: [],
  total: 0,
  page: 1,
  pageSize: 20,
  isLoading: false,
  error: null,

  fetchSessions: async (page = 1) => {
    set({ isLoading: true, error: null });
    try {
      const resp = await listSessionsApi(page, get().pageSize);
      set({
        sessions: resp.sessions,
        total: resp.total,
        page: resp.page,
        isLoading: false,
      });
    } catch (err: unknown) {
      set({ isLoading: false, error: extractError(err) });
    }
  },

  createSession: async (name: string) => {
    set({ error: null });
    try {
      const session = await createSessionApi({ session_name: name });
      
      await get().fetchSessions(get().page);
      return session;
    } catch (err: unknown) {
      const msg = extractError(err);
      set({ error: msg });
      throw new Error(msg);
    }
  },

  renameSession: async (id: string, name: string) => {
    set({ error: null });
    try {
      await updateSessionApi(id, { session_name: name });
      await get().fetchSessions(get().page);
    } catch (err: unknown) {
      set({ error: extractError(err) });
    }
  },

  deleteSession: async (id: string) => {
    set({ error: null });
    try {
      await deleteSessionApi(id);
      await get().fetchSessions(get().page);
    } catch (err: unknown) {
      set({ error: extractError(err) });
    }
  },

  clearError: () => set({ error: null }),
}));

import { extractErrorMessage } from "../utils/errors";

function extractError(err: unknown): string {
  return extractErrorMessage(err, "An unexpected error occurred");
}
