/**
 * Keepalive — renew the access token BEFORE it expires, so a request never
 * has to find out the hard way.
 *
 * The 401-then-retry path in `transport.ts` is the safety net; this is the
 * everyday path. Without it every request made in the last seconds of a
 * token's life would pay a failed round trip plus a refresh plus a retry, and
 * a request with side effects would be sent twice (harmless for this API's
 * create calls, since the first one was refused, but not free).
 *
 * The timer is not trusted alone. A laptop lid closes, a background tab's
 * timers are throttled to once a minute: so the app also checks on
 * `visibilitychange` ({@link Keepalive.wake}), and the 401 path covers whatever
 * both miss.
 */
import { tokenTimes, type RefreshOutcome } from "./refresh";

/** Renew this long before `exp`: 20 % of the token's life, 1 s..60 s. */
export function refreshLeadMs(issuedAt: number, expiresAt: number): number {
  return Math.min(60_000, Math.max(1_000, (expiresAt - issuedAt) * 0.2));
}

/** After a refresh that could not be ASKED (network, 5xx), try again this soon. */
export const RETRY_UNAVAILABLE_MS = 15_000;

export interface KeepaliveDeps {
  refresh: () => Promise<RefreshOutcome>;
  now: () => number;
  setTimer: (callback: () => void, delayMs: number) => unknown;
  clearTimer: (handle: unknown) => void;
}

export interface Keepalive {
  /** Plan the next renewal for *token* (null: signed out, plan nothing). */
  schedule(token: string | null): void;
  /** The page is visible again: renew now if the plan is already overdue. */
  wake(): void;
  stop(): void;
}

export function createKeepalive(deps: KeepaliveDeps): Keepalive {
  let timer: unknown = null;
  let current: string | null = null;
  let dueAt: number | null = null;
  /** `exp` of the token the last plan was made for (see `schedule`). */
  let plannedExpiry: number | null = null;

  const cancel = () => {
    if (timer !== null) deps.clearTimer(timer);
    timer = null;
  };

  const arm = (delayMs: number) => {
    cancel();
    dueAt = deps.now() + delayMs;
    timer = deps.setTimer(() => void fire(), Math.max(0, delayMs));
  };

  async function fire(): Promise<void> {
    timer = null;
    dueAt = null;
    const token = current;
    if (token === null) return;
    const outcome = await deps.refresh();
    // "refreshed" changes the stored token, and the store subscription
    // reschedules from the NEW token; "rejected" ends the session. Only a
    // refresh we could not even ask needs this module to try again.
    if (outcome.kind === "unavailable" && current === token && timer === null) {
      arm(RETRY_UNAVAILABLE_MS);
    }
  }

  return {
    schedule(token) {
      if (token !== null && token === current && timer !== null) return;
      cancel();
      dueAt = null;
      current = token;
      if (token === null) {
        plannedExpiry = null;
        return;
      }
      const times = tokenTimes(token);
      if (times === null) return; // unreadable: the 401 path alone applies
      // A renewal that did not move `exp` means the session has reached its
      // absolute bound (the gateway caps every token there). Planning another
      // renewal would only spin in the last second; the 401 path ends it.
      const previous = plannedExpiry;
      plannedExpiry = times.expiresAt;
      if (previous !== null && times.expiresAt <= previous) return;
      const lead = refreshLeadMs(times.issuedAt, times.expiresAt);
      arm(times.expiresAt - lead - deps.now());
    },
    wake() {
      if (current !== null && dueAt !== null && deps.now() >= dueAt) {
        cancel();
        void fire();
      }
    },
    stop() {
      cancel();
      current = null;
      dueAt = null;
      plannedExpiry = null;
    },
  };
}
