/**
 * Session renewal — trade the HttpOnly refresh cookie for a new access token.
 *
 * The gateway side (gateway.auth.security) makes every refresh token single
 * use: a second spend of the same token is treated as theft and ends the whole
 * session. So the one thing this module must never do is spend the same
 * cookie twice. Two mechanisms, for the two ways that could happen:
 *
 * - SINGLE FLIGHT, within a tab: however many requests hit a 401 at once, and
 *   whether the keepalive timer fires at the same moment, they share ONE
 *   refresh call and all wait for its answer.
 * - A WEB LOCK, across tabs: two tabs of the app share one cookie jar, so two
 *   tabs refreshing at the same instant would present the same cookie. The
 *   lock serialises them; the second tab's request then carries the cookie
 *   the first tab's response just set, which is a legitimate rotation. Where
 *   the Web Locks API is missing, single flight is all there is.
 *
 * Outcomes are three-valued on purpose. Only a 401 from the refresh route
 * means the session is over; a network failure, a 5xx or a 429 means "not
 * now", and signing an engineer out because the gateway blinked would be the
 * very defect this exists to remove.
 */
import type { GatewayClient } from "@loft/ts-client/gateway";

import type { SessionUser } from "./session";

export type RefreshOutcome =
  | { kind: "refreshed"; token: string; user: SessionUser }
  /** The refresh route said 401: revoked, expired, reused, or no cookie. */
  | { kind: "rejected" }
  /** Could not ask (network, 5xx, 429). The session may well be fine. */
  | { kind: "unavailable" };

/** Ask the gateway to rotate the refresh cookie (one HTTP call, no retries). */
export async function requestRefresh(
  client: GatewayClient,
): Promise<RefreshOutcome> {
  try {
    const { data, response } = await client.POST("/api/v1/auth/refresh");
    if (data !== undefined) {
      return { kind: "refreshed", token: data.access_token, user: data.user };
    }
    return response.status === 401
      ? { kind: "rejected" }
      : { kind: "unavailable" };
  } catch {
    return { kind: "unavailable" };
  }
}

/** Runs *task* while holding a lock (or directly, where there is none). */
export type LockRunner = <T>(task: () => Promise<T>) => Promise<T>;

/** The name every tab of the app locks on before spending the cookie. */
export const REFRESH_LOCK_NAME = "loft.auth.refresh";

/** A cross-tab lock over the Web Locks API; a pass-through without it. */
export function webLock(name: string = REFRESH_LOCK_NAME): LockRunner {
  return <T>(task: () => Promise<T>): Promise<T> => {
    const locks = (globalThis.navigator as Navigator | undefined)?.locks;
    if (locks === undefined || typeof locks.request !== "function") {
      return task();
    }
    return locks.request(name, () => task()) as Promise<T>;
  };
}

export interface RefresherDeps {
  /** The HTTP call (see {@link requestRefresh}). */
  request: () => Promise<RefreshOutcome>;
  lock?: LockRunner;
  /** A new access token for the live session. */
  onRefreshed: (token: string, user: SessionUser) => void;
  /** The session is over; send the user to sign in. */
  onRejected: () => void;
}

export interface Refresher {
  /** Renew now; concurrent callers share the one in-flight attempt. */
  refresh(): Promise<RefreshOutcome>;
}

export function createRefresher(deps: RefresherDeps): Refresher {
  const lock = deps.lock ?? ((task) => task());
  let inflight: Promise<RefreshOutcome> | null = null;
  return {
    refresh() {
      if (inflight !== null) return inflight;
      const attempt = (async () => {
        const outcome = await lock(deps.request);
        if (outcome.kind === "refreshed") {
          deps.onRefreshed(outcome.token, outcome.user);
        } else if (outcome.kind === "rejected") {
          deps.onRejected();
        }
        return outcome;
      })();
      inflight = attempt.finally(() => {
        inflight = null;
      });
      return inflight;
    },
  };
}

/** When an access token was issued and expires (epoch ms), from its claims. */
export interface TokenTimes {
  issuedAt: number;
  expiresAt: number;
}

/**
 * Read `iat`/`exp` out of a JWT WITHOUT verifying it — only the gateway can
 * verify, and this is scheduling, not trust. Null for anything unreadable, in
 * which case the 401 path alone keeps the session alive.
 */
export function tokenTimes(token: string): TokenTimes | null {
  const payload = token.split(".")[1];
  if (payload === undefined) return null;
  try {
    const json = atob(payload.replace(/-/g, "+").replace(/_/g, "/"));
    const claims = JSON.parse(json) as Record<string, unknown>;
    const { iat, exp } = claims;
    if (typeof exp !== "number" || !Number.isFinite(exp)) return null;
    const issued = typeof iat === "number" && Number.isFinite(iat) ? iat : exp;
    return { issuedAt: issued * 1000, expiresAt: exp * 1000 };
  } catch {
    return null;
  }
}
