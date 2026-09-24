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

import {
  clearAllSketchDrafts,
  sweepSketchDrafts,
  writeEvictingDrafts,
} from "../routes/sketchDraft";
import { defaultStorage, type SessionStorageLike } from "./storage";

// The seam lives in `./storage` (a leaf, so `sketchDraft.ts` can use its
// helpers without an import cycle); re-exported so existing consumers keep
// importing it from here.
export type { SessionStorageLike } from "./storage";

export type SessionUser = components["schemas"]["UserResponse"];

export const SESSION_STORAGE_KEY = "loft.session.v1";

/**
 * What the user is told when a sign-in could not be written down. The
 * in-memory session still works; only the next reload loses it.
 */
export const SESSION_NOT_PERSISTED_MESSAGE =
  "This browser would not save your session — you will be signed out when the page reloads.";

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
  /**
   * Non-null when the last sign-in could NOT be written to storage, even
   * after evicting every sketch draft to make room — the session works until
   * the next reload and no longer. {@link SESSION_NOT_PERSISTED_MESSAGE} is
   * the text; chrome that shows it reads it from here. Cleared by the next
   * successful write and by sign-out.
   */
  persistError: string | null;
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

/**
 * Write the session down, making room if the storage is full. Returns null on
 * success, or the user-facing error when it could not be written.
 *
 * W0REV-3: this used to swallow every failure, so a quota filled by sketch
 * drafts made sign-in look fine and then "logged the user out" on reload,
 * with nothing anywhere pointing at the cause. A full storage now evicts
 * drafts oldest-first before giving up — a stale unsaved sketch from another
 * part is worth less than staying signed in — and a write that STILL fails
 * (private mode, storage switched off, a quota filled by something that is not
 * ours) is reported: in the store, for the chrome, and on the console.
 */
function persist(
  storage: SessionStorageLike,
  session: PersistedSession,
): string | null {
  const serialized = JSON.stringify(session);
  const written = writeEvictingDrafts(storage, () =>
    storage.setItem(SESSION_STORAGE_KEY, serialized),
  );
  if (written.ok) return null;
  console.error(
    `[loft] session not persisted (evicted ${written.evicted} sketch draft(s) first):`,
    written.error,
  );
  return SESSION_NOT_PERSISTED_MESSAGE;
}

function clearPersisted(storage: SessionStorageLike) {
  try {
    storage.removeItem(SESSION_STORAGE_KEY);
  } catch {
    // Same posture as persist().
  }
}

/**
 * THE END OF A SESSION ENDS THE SESSION'S WORK ON DISK (W0 review finding 4).
 *
 * Sign-out used to remove the token and nothing else, leaving every unsaved
 * sketch draft readable for seven days — and `draftKey` is keyed on the PART,
 * not on the person, so on a shared browser the next user to open that part id
 * had the previous user's geometry restored into their session and could save
 * it into the part under their own name.
 *
 * Deleting the bytes is the fix rather than keying the drafts per user: a
 * user-scoped key hides the geometry from the next person but leaves it on
 * their disk for a week, which is the other half of the same finding. It also
 * needs an owner id at every read and write, i.e. a change in `PartPage`.
 *
 * Applied to `expire()` as well, deliberately, and the trade is worth naming:
 * an involuntary token expiry drops the draft of the user it belonged to. That
 * costs an edge case a recovery it might have wanted; keeping it would leave
 * the shared-browser hole open through the one path that does not go through
 * sign-out (A's token expires, B signs in). The live save loop is the recovery
 * for work that matters, and it runs the whole time the token is valid.
 */
function clearSessionScopedWork(storage: SessionStorageLike) {
  clearPersisted(storage);
  clearAllSketchDrafts(storage);
}

/**
 * Build a session store over *storage* (tests inject a fake).
 *
 * Creating the store is app start, so it is also where the sketch drafts are
 * swept (W0REV-3): expired and over-budget drafts go BEFORE anything else in
 * this session needs room — the sign-in write above all.
 */
export function createSessionStore(
  storage: SessionStorageLike,
  now: number = Date.now(),
) {
  sweepSketchDrafts(storage, now);
  const initial = loadPersisted(storage);
  return create<SessionState>()((set) => ({
    token: initial?.token ?? null,
    user: initial?.user ?? null,
    expired: false,
    persistError: null,
    signIn: (token, user) => {
      const persistError = persist(storage, { token, user });
      set({ token, user, expired: false, persistError });
    },
    signOut: () => {
      clearSessionScopedWork(storage);
      set({ token: null, user: null, expired: false, persistError: null });
    },
    expire: () => {
      clearSessionScopedWork(storage);
      set({ token: null, user: null, expired: true, persistError: null });
    },
  }));
}

/** THE app session store (browser localStorage-backed). */
export const useSessionStore = createSessionStore(defaultStorage());
