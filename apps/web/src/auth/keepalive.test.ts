import { describe, expect, it } from "vitest";

import {
  createKeepalive,
  refreshLeadMs,
  RETRY_UNAVAILABLE_MS,
} from "./keepalive";
import type { RefreshOutcome } from "./refresh";
import { fakeJwt } from "./testing";

/** A manual clock + timer queue, so the tests say exactly when things fire. */
function harness(outcomes: RefreshOutcome[]) {
  let now = 0;
  const timers = new Map<number, { at: number; callback: () => void }>();
  let nextId = 1;
  const refreshes: number[] = [];
  const keepalive = createKeepalive({
    refresh: async () => {
      refreshes.push(now);
      return outcomes.shift() ?? { kind: "unavailable" };
    },
    now: () => now,
    setTimer: (callback, delayMs) => {
      const id = nextId++;
      timers.set(id, { at: now + delayMs, callback });
      return id;
    },
    clearTimer: (handle) => void timers.delete(handle as number),
  });
  /** Move the clock to *to*, firing every timer due on the way. */
  async function advance(to: number) {
    for (;;) {
      const due = [...timers.entries()]
        .filter(([, t]) => t.at <= to)
        .sort((a, b) => a[1].at - b[1].at)[0];
      if (due === undefined) break;
      timers.delete(due[0]);
      now = due[1].at;
      due[1].callback();
      await Promise.resolve();
      await Promise.resolve();
    }
    now = to;
  }
  return {
    keepalive,
    refreshes,
    advance,
    pending: () => timers.size,
    setNow: (t: number) => {
      now = t;
    },
  };
}

/** A token issued at *iat* s living *ttl* s. */
const token = (iat: number, ttl: number) => fakeJwt({ iat, exp: iat + ttl });

describe("refreshLeadMs", () => {
  it("is 20 % of the lifetime, clamped to 1 s..60 s", () => {
    expect(refreshLeadMs(0, 3_600_000)).toBe(60_000);
    expect(refreshLeadMs(0, 20_000)).toBe(4_000);
    expect(refreshLeadMs(0, 2_000)).toBe(1_000);
  });
});

describe("createKeepalive", () => {
  it("renews before expiry, not after", async () => {
    const h = harness([{ kind: "unavailable" }]);
    h.keepalive.schedule(token(0, 3600));
    await h.advance(3_539_999);
    expect(h.refreshes).toEqual([]);
    await h.advance(3_540_000);
    expect(h.refreshes).toEqual([3_540_000]); // 60 s before exp
  });

  it("a renewed token plans the next renewal from ITS expiry", async () => {
    const h = harness([]);
    h.keepalive.schedule(token(0, 20));
    h.keepalive.schedule(token(16, 20)); // what a refresh at 16 s stores
    await h.advance(31_999);
    expect(h.refreshes).toEqual([]);
    await h.advance(32_000);
    expect(h.refreshes).toEqual([32_000]);
  });

  it("an already-expired token (a reopened tab) renews at once", async () => {
    const h = harness([]);
    h.setNow(10_000_000);
    h.keepalive.schedule(token(0, 3600));
    await h.advance(10_000_000);
    expect(h.refreshes).toEqual([10_000_000]);
  });

  it("an unreachable gateway is retried, not taken as the end", async () => {
    const h = harness([{ kind: "unavailable" }, { kind: "unavailable" }]);
    h.keepalive.schedule(token(0, 20));
    await h.advance(16_000);
    await h.advance(16_000 + RETRY_UNAVAILABLE_MS);
    expect(h.refreshes).toEqual([16_000, 16_000 + RETRY_UNAVAILABLE_MS]);
  });

  it("a rejected refresh stops the plan (the session is over)", async () => {
    const h = harness([{ kind: "rejected" }]);
    h.keepalive.schedule(token(0, 20));
    await h.advance(16_000);
    await h.advance(1_000_000);
    expect(h.refreshes).toEqual([16_000]);
  });

  it("signing out cancels the plan", async () => {
    const h = harness([]);
    h.keepalive.schedule(token(0, 20));
    h.keepalive.schedule(null);
    await h.advance(1_000_000);
    expect(h.refreshes).toEqual([]);
    expect(h.pending()).toBe(0);
  });

  it("scheduling the same token twice keeps one plan", async () => {
    const h = harness([]);
    h.keepalive.schedule(token(0, 20));
    h.keepalive.schedule(token(0, 20));
    expect(h.pending()).toBe(1);
    await h.advance(16_000);
    expect(h.refreshes).toEqual([16_000]);
  });

  it("wake() renews an overdue plan (a timer that slept with the laptop)", async () => {
    const h = harness([]);
    h.keepalive.schedule(token(0, 20));
    h.setNow(30_000); // the lid was closed; the timer never ran
    h.keepalive.wake();
    await Promise.resolve();
    expect(h.refreshes).toEqual([30_000]);
  });

  it("at the session's absolute bound (exp no longer moves) it stops planning", async () => {
    const h = harness([]);
    h.keepalive.schedule(token(0, 20)); // exp 20 s
    h.keepalive.schedule(fakeJwt({ iat: 19, exp: 20 })); // capped: same exp
    await h.advance(1_000_000);
    expect(h.refreshes).toEqual([]);
  });
});
