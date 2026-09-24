/**
 * Auth transport — wires the session into the ONE gateway client:
 *
 * - every request carries `Authorization: Bearer <token>` while signed in;
 * - a 401 whose envelope code is `invalid_token` (expired, tampered, revoked,
 *   or ghost-user token — the gateway is deliberately uniform) no longer ends
 *   the session on the spot. The session is renewed from the refresh cookie
 *   and the request is sent ONCE more with the new token; the caller sees the
 *   retried response and never learns there was a gap. Only when the renewal
 *   itself is refused does the session end (the quiet "session expired"
 *   notice, and sign-in returns the user to where they were).
 * - Login's `invalid_credentials` 401 is NOT a session defect and passes
 *   through untouched, as does every 401 from the session routes themselves.
 *
 * Tokens are renewed BEFORE they expire too (`keepalive.ts`); the path here is
 * the safety net for a sleeping laptop, a throttled tab, or a token the
 * gateway revoked.
 */
import type { Middleware } from "openapi-fetch";

import { envelopeCode } from "../api/envelope";
import { gatewayClient } from "../api/client";
import { createKeepalive } from "./keepalive";
import {
  createRefresher,
  requestRefresh,
  webLock,
  type RefreshOutcome,
} from "./refresh";
import { useSessionStore } from "./session";

/** What the middleware needs from the session (injectable for tests). */
export interface SessionTransport {
  getToken(): string | null;
  /** Who this tab is signed in as — requests are only ever resent as them. */
  getUserId(): string | null;
  /** Renew the session (single flight; see `refresh.ts`). */
  refresh(): Promise<RefreshOutcome>;
  /** The session cannot continue: clear it and send the user to sign in. */
  expire(): void;
}

/**
 * The session routes. Their 401s are answers ABOUT the session (bad password,
 * spent cookie) and must never trigger a renewal, or a failed refresh would
 * try to refresh itself.
 */
export const SESSION_ROUTES: ReadonlySet<string> = new Set([
  "/api/v1/auth/login",
  "/api/v1/auth/register",
  "/api/v1/auth/refresh",
  "/api/v1/auth/logout",
]);

async function isInvalidToken(response: Response): Promise<boolean> {
  if (response.status !== 401) return false;
  try {
    return envelopeCode(await response.clone().json()) === "invalid_token";
  } catch {
    return false; // Non-JSON 401 — not ours to interpret.
  }
}

function bearerOf(request: Request): string | null {
  const header = request.headers.get("Authorization");
  return header?.startsWith("Bearer ") ? header.slice("Bearer ".length) : null;
}

export function createAuthMiddleware(
  session: SessionTransport,
  fetchImpl?: (request: Request) => Promise<Response>,
): Middleware {
  // A body can be read once and `fetch` has read it, so a request that might
  // need a retry keeps an unread copy. Keyed on the Request object, so the
  // copy goes when the request does. The price is that the copy holds the
  // body in memory until then: small for JSON, a transient second copy for a
  // STEP upload.
  const replays = new WeakMap<Request, Request>();
  // The user each request was SENT as. A resend goes out only as that same
  // user: never replay one person's write under another person's token.
  const sentAs = new WeakMap<Request, string | null>();
  return {
    async onRequest({ request, schemaPath }) {
      sentAs.set(request, session.getUserId());
      const token = session.getToken();
      if (token !== null) {
        request.headers.set("Authorization", `Bearer ${token}`);
      }
      if (!SESSION_ROUTES.has(schemaPath) && request.body !== null) {
        replays.set(request, request.clone());
      }
      return request;
    },
    async onResponse({ request, response, schemaPath, options }) {
      if (SESSION_ROUTES.has(schemaPath)) return response;
      if (!(await isInvalidToken(response))) return response;

      // Another request may already have renewed the session while this one
      // was in flight: then there is nothing to renew, only to resend.
      const sent = bearerOf(request);
      const held = session.getToken();
      let token: string | null = held !== null && held !== sent ? held : null;
      if (token === null) {
        const outcome = await session.refresh();
        // "rejected" has already ended the session (see installAuthTransport);
        // "unavailable" keeps it — this call fails like any network blip, and
        // the keepalive tries again.
        if (outcome.kind !== "refreshed") return response;
        token = outcome.token;
      }
      const owner = sentAs.get(request) ?? null;
      if (owner === null || session.getUserId() !== owner) return response;

      const replay = replays.get(request) ?? new Request(request);
      replays.delete(request);
      replay.headers.set("Authorization", `Bearer ${token}`);
      // Detached on purpose: `options.fetch(...)` would call the browser's
      // fetch with `this` = the options object, and Chromium throws "Illegal
      // invocation". Node's fetch does not check its receiver; the scripted
      // fetch in transport.test.ts does, so the unit suite catches it too.
      const clientFetch = options.fetch;
      const send = fetchImpl ?? clientFetch;
      const retried = await send(replay);
      // Retried once, with a token minted this instant: a second invalid_token
      // is not an expiry to ride out, it is a session that cannot work.
      if (await isInvalidToken(retried)) session.expire();
      return retried;
    },
  };
}

/** Where the user is now — what sign-in should return them to. */
function currentPath(): string | null {
  const location = globalThis.location as Location | undefined;
  if (location === undefined) return null;
  return `${location.pathname}${location.search}${location.hash}`;
}

/** Revoke the session server-side (fire and forget; sign-out already happened). */
async function revokeOnServer(token: string): Promise<void> {
  try {
    await gatewayClient.POST("/api/v1/auth/logout", {
      headers: { Authorization: `Bearer ${token}` },
    });
  } catch {
    // Offline: the server-side session then lives on until its idle bound
    // (the next sign-in replaces the cookie). Nothing the user can act on.
  }
}

let installed = false;

/**
 * Install the auth middleware and the keepalive on the app's gateway client
 * (idempotent). Also: a deliberate sign-out revokes the session server-side,
 * so the refresh cookie and every access token of it stop working at once.
 */
export function installAuthTransport(): void {
  if (installed) return;
  installed = true;
  const store = useSessionStore;
  const expire = () => {
    if (store.getState().token !== null) store.getState().expire(currentPath());
  };
  const refresher = createRefresher({
    request: () => requestRefresh(gatewayClient),
    lock: webLock(),
    onRefreshed: (token, user) => {
      // A sign-out while the refresh was in flight wins: do not sign back in.
      if (store.getState().token !== null) store.getState().signIn(token, user);
    },
    onRejected: expire,
    currentUserId: () => store.getState().user?.id ?? null,
    onSwitched: () => store.getState().abandon(),
  });
  gatewayClient.use(
    createAuthMiddleware({
      getToken: () => store.getState().token,
      getUserId: () => store.getState().user?.id ?? null,
      refresh: () => refresher.refresh(),
      expire,
    }),
  );

  const keepalive = createKeepalive({
    refresh: () => refresher.refresh(),
    now: () => Date.now(),
    setTimer: (callback, delayMs) => globalThis.setTimeout(callback, delayMs),
    clearTimer: (handle) =>
      globalThis.clearTimeout(handle as ReturnType<typeof setTimeout>),
  });
  keepalive.schedule(store.getState().token);
  store.subscribe((state, previous) => {
    if (state.token !== previous.token) keepalive.schedule(state.token);
    if (previous.token !== null && state.token === null && !state.expired) {
      void revokeOnServer(previous.token);
    }
  });
  globalThis.document?.addEventListener("visibilitychange", () => {
    if (globalThis.document.visibilityState === "visible") keepalive.wake();
  });
}
