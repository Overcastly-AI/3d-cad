/**
 * Session state — the signed-in identity, shared by the transport middleware
 * (bearer header), the route gate, and the chrome (user cell + sign out).
 *
 * Persistence: the token + user are mirrored to localStorage so a reload
 * keeps the session (backlog #7 acceptance). SECURITY TRADEOFF, v1 by
 * decision: localStorage is readable by any script that achieves XSS, unlike
 * an httpOnly cookie. Accepted for v1 because tokens live 1 h with no
 * refresh, the app ships no third-party runtime scripts, and expired/invalid
 * tokens are caught globally (see transport.ts) — the httpOnly-cookie
 * migration is a tracked later item (see the 2026-07-10 changelog entry).
 */
import type { components } from "@loft/ts-client/gateway";
import { create } from "zustand";

export type SessionUser = components["schemas"]["UserResponse"];

export const SESSION_STORAGE_KEY = "loft.session.v1";

/** The subset of the Storage API the store needs (injectable for tests). */
export interface SessionStorageLike {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

interface PersistedSession {
  token: string;
  user: SessionUser;
}

export interface SessionState {
  /** Bearer token, or null when signed out. */
  token: string | null;
  user: SessionUser | null;
  /** True after a global invalid-token catch — the quiet sign-in notice. */
  expired: boolean;
  /** Store a fresh session (register/login success). Clears `expired`. */
  signIn: (token: string, user: SessionUser) => void;
  /** Deliberate sign-out — clears the session without a notice. */
  signOut: () => void;
  /** Invalid/expired token — clears the session AND flags the notice. */
  expire: () => void;
}

function isSessionUser(v: unknown): v is SessionUser {
  if (typeof v !== "object" || v === null) return false;
  const o = v as Record<string, unknown>;
  return (
    typeof o.id === "string" &&
    typeof o.email === "string" &&
    typeof o.created_at === "string"
  );
}

function loadPersisted(storage: SessionStorageLike): PersistedSession | null {
  try {
    const raw = storage.getItem(SESSION_STORAGE_KEY);
    if (raw === null) return null;
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null) return null;
    const o = parsed as Record<string, unknown>;
    if (typeof o.token !== "string" || !isSessionUser(o.user)) return null;
    return { token: o.token, user: o.user };
  } catch {
    // Corrupt JSON or a storage that throws — treat as signed out.
    return null;
  }
}

function persist(storage: SessionStorageLike, session: PersistedSession) {
  try {
    storage.setItem(SESSION_STORAGE_KEY, JSON.stringify(session));
  } catch {
    // Quota/private-mode failure: the in-memory session still works; only
    // reload persistence is lost.
  }
}

function clearPersisted(storage: SessionStorageLike) {
  try {
    storage.removeItem(SESSION_STORAGE_KEY);
  } catch {
    // Same posture as persist().
  }
}

/** Build a session store over *storage* (tests inject a fake). */
export function createSessionStore(storage: SessionStorageLike) {
  const initial = loadPersisted(storage);
  return create<SessionState>()((set) => ({
    token: initial?.token ?? null,
    user: initial?.user ?? null,
    expired: false,
    signIn: (token, user) => {
      persist(storage, { token, user });
      set({ token, user, expired: false });
    },
    signOut: () => {
      clearPersisted(storage);
      set({ token: null, user: null, expired: false });
    },
    expire: () => {
      clearPersisted(storage);
      set({ token: null, user: null, expired: true });
    },
  }));
}

/** No-op storage for environments without localStorage (SSR, unit tests). */
const nullStorage: SessionStorageLike = {
  getItem: () => null,
  setItem: () => undefined,
  removeItem: () => undefined,
};

function defaultStorage(): SessionStorageLike {
  try {
    return globalThis.localStorage ?? nullStorage;
  } catch {
    return nullStorage;
  }
}

/** THE app session store (browser localStorage-backed). */
export const useSessionStore = createSessionStore(defaultStorage());
