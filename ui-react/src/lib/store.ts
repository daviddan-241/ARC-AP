import { create } from "zustand";
import type { ChatMessage } from "./api";

export type ThoughtStep = {
  id: string;
  label: string;
  detail?: string;
  state: "running" | "ok" | "failed";
};

export type SourceResult = {
  url: string;
  domain: string;
  title: string;
  snippet: string;
  ago?: string;
  logo?: string; // favicon URL
};

/** Zustand store — the single source of truth for chat + thoughts + browser. */
interface AppState {
  // auth
  authed: boolean;
  pinOk: boolean;
  setAuthed: (v: boolean) => void;
  setPinOk: (v: boolean) => void;

  // chat
  conversationId: string | null;
  messages: ChatMessage[];
  thinking: boolean;
  mood: string;
  quickReplies: string[];
  setConversation: (id: string | null) => void;
  addMessage: (m: ChatMessage) => void;
  setThinking: (v: boolean) => void;
  setMood: (m: string) => void;
  setQuickReplies: (replies: string[]) => void;
  resetChat: () => void;

  // thoughts
  thoughtsOpen: boolean;
  steps: ThoughtStep[];
  sources: SourceResult[];
  setThoughtsOpen: (v: boolean) => void;
  addStep: (label: string, detail?: string) => string;
  resolveStep: (id: string, ok: boolean, detail?: string) => void;
  addSources: (s: SourceResult[]) => void;
  clearThoughts: () => void;

  // in-app browser
  browserOpen: boolean;
  browserUrl: string;
  browserPage: "arena" | "webmail";
  openBrowser: (url: string, page?: "arena" | "webmail") => void;
  closeBrowser: () => void;
}

let stepSeq = 0;

export const useStore = create<AppState>((set) => ({
  authed: false,
  pinOk: false,
  setAuthed: (v) => set({ authed: v }),
  setPinOk: (v) => set({ pinOk: v }),

  conversationId: localStorage.getItem("conversationId") || null,
  messages: [],
  thinking: false,
  mood: localStorage.getItem("mood") || "uncensored",
  quickReplies: [],
  setConversation: (id) => {
    localStorage.setItem("conversationId", id ?? "");
    set({ conversationId: id, messages: [], steps: [], sources: [] });
  },
  addMessage: (m) => set((s) => ({ messages: [...s.messages, m] })),
  setThinking: (v) => set({ thinking: v }),
  setMood: (m) => {
    localStorage.setItem("mood", m);
    set({ mood: m });
  },
  setQuickReplies: (replies) => set({ quickReplies: replies }),
  resetChat: () => set({ messages: [], steps: [], sources: [], quickReplies: [] }),

  thoughtsOpen: false,
  steps: [],
  sources: [],
  setThoughtsOpen: (v) => set({ thoughtsOpen: v }),
  addStep: (label, detail) => {
    const id = `step-${++stepSeq}`;
    set((s) => ({ steps: [...s.steps, { id, label, detail, state: "running" }], thoughtsOpen: true }));
    return id;
  },
  resolveStep: (id, ok, detail) =>
    set((s) => ({
      steps: s.steps.map((st) => (st.id === id ? { ...st, state: ok ? "ok" : "failed", detail: detail ?? st.detail } : st)),
    })),
  addSources: (sources) => set((s) => ({ sources: [...s.sources, ...sources] })),
  clearThoughts: () => set({ steps: [], sources: [] }),

  browserOpen: false,
  browserUrl: "https://arena.ai",
  browserPage: "arena",
  openBrowser: (url, page = "arena") => set({ browserOpen: true, browserUrl: url, browserPage: page }),
  closeBrowser: () => set({ browserOpen: false }),
}));

/** Favicon helper for source cards (real Google favicon service). */
export const faviconUrl = (domain: string) =>
  `https://www.google.com/s2/favicons?domain=${encodeURIComponent(domain)}&sz=64`;
