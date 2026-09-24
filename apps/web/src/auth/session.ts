/**
 * Session state — the signed-in identity, shared by the transport middleware
 * (bearer header), the route gate, and the chrome (user cell + sign out).
 *
 * Persistence: the ACCESS token + user are mirrored to localStorage so a
 * reload keeps the session (backlog #7 acceptance). SECURITY TRADEOFF, by
 * decision: localStorage is readable by any script that achieves XSS. What
 * bounds it is the split the gateway makes (gateway.auth.security): the
 * access token is short-lived and dies with its session on logout or reuse
 * detection, while the long-lived credential — the refresh token — lives only
 * in an HttpOnly cookie no script can read. A script running in the page can
 * still ASK for new access tokens while it runs (same-origin fetch sends the
 * cookie); it cannot carry a lasting credential away. The app ships no
 * third-party runtime scripts. Renewal is `refresh.ts` + `keepalive.ts`;
 * invalid tokens are caught globally in `transport.ts`.
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
 * in-memory session still works; only the next reload loses it. What
 * happened, then the two things that actually help.
 */
export const SESSION_NOT_PERSISTED_MESSAGE =
  "This browser would not store your sign-in, so reloading or closing this tab will sign you out. Free up storage for this site in your browser settings, or keep this tab open.";

/**
 * The same condition seen BEFORE sign-in: the sign-in page probes storage on
 * arrival (see {@link probeSessionPersistence}) because once a sign-in
 * succeeds the page is left at once, so a failure found then can only be
 * reported by the chrome the user lands in.
 */
export const SIGN_IN_WILL_NOT_PERSIST_MESSAGE =
  "This browser is not storing sign-ins right now, so after you sign in, reloading or closing this tab will sign you out. Free up storage for this site in your browser settings, or keep the tab open.";

/** A write the size of a real session (token + user), for the probe. */
const PROBE_KEY = `${SESSION_STORAGE_KEY}.probe`;
const PROBE_VALUE = "x".repeat(1024);

/**
 * Whether a sign-in written now would survive a reload: null if it would, the
 * user-facing message if it would not.
 *
 * It asks the storage the same way sign-in will — a session-sized write
 * through the same draft eviction — and removes the probe afterwards, so it
 * leaves nothing behind but the room it made. Never throws.
 */
export function probeSessionPersistence(
  storage: SessionStorageLike = defaultStorage(),
): string | null {
  const written = writeEvictingDrafts(storage, () =>
    storage.setItem(PROBE_KEY, PROBE_VALUE),
  );
  try {
    storage.removeItem(PROBE_KEY);
  } catch {
    // Nothing further to do; the answer below is already known.
  }
  return written.ok ? null : SIGN_IN_WILL_NOT_PERSIST_MESSAGE;
}

/** Stands in for the page origin where there is no page (unit tests, SSR). */
const NO_PAGE_ORIGIN = "http://localhost";

/**
 * Where to send the user after they sign in again: a path INSIDE this app, or
 * null, so a crafted value can never turn sign-in into an open redirect.
 *
 * Decided the way the browser will decide, not by pattern-matching the
 * string: the path is resolved by the URL parser against this origin, must
 * stay on it, and is then RE-SERIALISED from the parsed parts. The parser
 * strips tabs and newlines and reads backslashes as slashes, which is exactly
 * how "/\t/evil.com" and "/\\evil.com" become another host. The serialised
 * result is checked again, because normalisation can also CREATE a
 * protocol-relative href: "/..//evil.com" parses on-origin with the path
 * "//evil.com". The sign-in page itself is refused (a loop).
 */
export function safeReturnPath(
  path: string | null | undefined,
  origin: string = (globalThis.location as Location | undefined)?.origin ??
    NO_PAGE_ORIGIN,
): string | null {
  if (typeof path !== "string" || !path.startsWith("/")) return null;
  let url: URL;
  try {
    url = new URL(path, origin);
  } catch {
    return null;
  }
  if (url.origin !== origin) return null;
  const serialised = `${url.pathname}${url.search}${url.hash}`;
  if (!serialised.startsWith("/") || serialised.startsWith("//")) return null;
  if (url.pathname === "/sign-in" || url.pathname.startsWith("/sign-in/")) {
    return null;
  }
  return serialised;
}

interface PersistedSession {
  token: string;
  user: SessionUser;
  /** This client's `Date.now()` when the token arrived (keepalive.ts). */
  receivedAt?: number;
}

export interface SessionState {
  /** Bearer token, or null when signed out. */
  token: string | null;
  /**
   * When this client received `token`, by ITS clock (never compared with the
   * token's own server-clock claims — see keepalive.ts). Null when unknown.
   */
  receivedAt: number | null;
  user: SessionUser | null;
  /** True after a global invalid-token catch — the quiet sign-in notice. */
  expired: boolean;
  /**
   * The in-app path sign-in sends the user to (see {@link safeReturnPath}):
   * where they were when the session ended involuntarily, or the page a
   * signed-out visit asked for ({@link SessionState.rememberDeepLink}). Null
   * after a deliberate sign-out, and cleared once used.
   */
  returnTo: string | null;
  /** Sign-in has used {@link SessionState.returnTo}; forget it. */
  clearReturnTo: () => void;
  /**
   * A signed-out visit to a page behind sign-in (a deep link, a bookmark, a
   * shared URL): sign-in goes there next (DEEPLINK-SIGNIN-RETURN-1).
   *
   * Only while no session has ended in this page. After a deliberate
   * sign-out the next sign-in goes home, as it always did. After an expiry,
   * `expire` has already recorded the path, together with whose it is, and
   * this must not overwrite that. After `abandon`, the page is someone
   * else's. A no-op while signed in.
   */
  rememberDeepLink: (path: string | null) => void;
  /**
   * Non-null when the last sign-in could NOT be written to storage, even
   * after evicting every sketch draft to make room — the session works until
   * the next reload and no longer. {@link SESSION_NOT_PERSISTED_MESSAGE} is
   * the text; the top bar shows it from here. Cleared by the next successful
   * write, by sign-out, and by the user dismissing it.
   */
  persistError: string | null;
  /** The user has read the persistence notice; stop showing it. */
  dismissPersistError: () => void;
  /**
   * Store a fresh session: register/login success, and every silent refresh
   * (a refresh is a new access token for the same session, so it takes the
   * same path). Clears `expired`; leaves `returnTo` for the sign-in page.
   */
  signIn: (token: string, user: SessionUser) => void;
  /** Deliberate sign-out — clears the session without a notice. */
  signOut: () => void;
  /**
   * The session could not be renewed — clears it AND flags the notice.
   * `returnTo` is where the user was, so sign-in can take them back.
   */
  expire: (returnTo?: string | null) => void;
  /**
   * The browser's sign-in now belongs to someone ELSE (another tab signed in
   * as a different user). This tab forgets its session and shows the notice,
   * and touches nothing in storage: the stored session and the drafts there
   * are the other user's now, and clearing them would sign THEM out.
   */
  abandon: () => void;
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
    const receivedAt =
      typeof o.receivedAt === "number" && Number.isFinite(o.receivedAt)
        ? o.receivedAt
        : undefined;
    return { token: o.token, user: o.user, receivedAt };
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
  // Whose return path `returnTo` is: a different user signing in next does
  // not inherit it (it would open the previous user's part).
  let returnOwner: string | null = null;
  // Set by every way a session ends here; see rememberDeepLink.
  let sessionEnded = false;
  return create<SessionState>()((set, get) => ({
    token: initial?.token ?? null,
    receivedAt: initial?.receivedAt ?? null,
    user: initial?.user ?? null,
    expired: false,
    returnTo: null,
    clearReturnTo: () => set({ returnTo: null }),
    rememberDeepLink: (path) => {
      if (sessionEnded || get().token !== null) return;
      // No owner: whoever signs in asked for this page themselves.
      set({ returnTo: safeReturnPath(path) });
    },
    persistError: null,
    dismissPersistError: () => set({ persistError: null }),
    signIn: (token, user) => {
      const receivedAt = Date.now();
      const persistError = persist(storage, { token, user, receivedAt });
      const keepReturn = returnOwner === null || returnOwner === user.id;
      set({
        token,
        receivedAt,
        user,
        expired: false,
        persistError,
        ...(keepReturn ? {} : { returnTo: null }),
      });
    },
    signOut: () => {
      sessionEnded = true;
      clearSessionScopedWork(storage);
      set({
        token: null,
        user: null,
        expired: false,
        returnTo: null,
        persistError: null,
      });
    },
    expire: (returnTo) => {
      sessionEnded = true;
      returnOwner = get().user?.id ?? null;
      clearSessionScopedWork(storage);
      set({
        token: null,
        user: null,
        expired: true,
        returnTo: safeReturnPath(returnTo),
        persistError: null,
      });
    },
    abandon: () => {
      sessionEnded = true;
      returnOwner = null;
      set({
        token: null,
        user: null,
        expired: true,
        returnTo: null,
        persistError: null,
      });
    },
  }));
}

/** THE app session store (browser localStorage-backed). */
export const useSessionStore = createSessionStore(defaultStorage());
