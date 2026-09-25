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

  it("a renewed token plans the next renewal from when IT arrived", async () => {
    const h = harness([]);
    h.keepalive.schedule(token(0, 20), 0);
    h.setNow(16_000);
    h.keepalive.schedule(token(16, 20), 16_000); // what a refresh at 16 s stores
    await h.advance(31_999);
    expect(h.refreshes).toEqual([]);
    await h.advance(32_000);
    expect(h.refreshes).toEqual([32_000]);
  });

  it("a token received long ago (a reopened tab) renews at once", async () => {
    const h = harness([]);
    h.setNow(10_000_000);
    h.keepalive.schedule(token(0, 3600), 0); // received 10 000 s ago
    await h.advance(10_000_000);
    expect(h.refreshes).toEqual([10_000_000]);
  });

  it("a token of unknown age (stored before receipt was recorded) counts as fresh", async () => {
    const h = harness([]);
    h.setNow(10_000_000);
    h.keepalive.schedule(token(0, 3600), null);
    await h.advance(10_000_000 + 3_539_999);
    expect(h.refreshes).toEqual([]);
    await h.advance(10_000_000 + 3_540_000);
    expect(h.refreshes).toEqual([10_000_000 + 3_540_000]);
  });

  // Review S2: the server's `iat`/`exp` and this machine's clock are never
  // compared. The reviewer's probe: a client clock 2 h fast, tokens minted by
  // the server with a 1000 ms or a sub-second round trip. It used to renew in a
  // zero-delay loop, or stop planning for good.
  it.each([1_000, 200])(
    "a client clock 2 h fast (round trip %i ms) renews once per token lifetime",
    async (roundTripMs) => {
      const skewMs = 2 * 3600 * 1000;
      let serverNow = 1_700_000_000_000;
      const mint = () => {
        const iat = Math.floor(serverNow / 1000);
        return fakeJwt({ iat, exp: iat + 3600 });
      };
      let clientNow = serverNow + skewMs;
      const timers: { at: number; callback: () => void }[] = [];
      const refreshes: number[] = [];
      const keepalive = createKeepalive({
        now: () => clientNow,
        setTimer: (callback, delayMs) => {
          timers.push({ at: clientNow + delayMs, callback });
          return timers.length;
        },
        clearTimer: () => undefined,
        refresh: async () => {
          refreshes.push(clientNow);
          serverNow += roundTripMs;
          clientNow += roundTripMs;
          keepalive.schedule(mint(), clientNow); // as the store subscription does
          return { kind: "refreshed", token: "unused", user: {} as never };
        },
      });
      keepalive.schedule(mint(), clientNow);
      const start = clientNow;
      // Run three hours of the client's timeline.
      while (timers.length > 0) {
        timers.sort((a, b) => a.at - b.at);
        const next = timers.shift();
        if (next === undefined || next.at > start + 3 * 3600 * 1000) break;
        const advance = next.at - clientNow;
        clientNow = next.at;
        serverNow += advance;
        next.callback();
        await Promise.resolve();
        await Promise.resolve();
      }
      expect(refreshes).toHaveLength(3);
      expect(refreshes[0]! - start).toBe(3_540_000); // 60 s before the end
      expect(refreshes[1]! - refreshes[0]!).toBe(3_540_000 + roundTripMs);
    },
  );

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

  it("at the session's absolute bound (a token too short to renew ahead) it stops planning", async () => {
    const h = harness([]);
    h.keepalive.schedule(fakeJwt({ iat: 19, exp: 20 }), 0); // capped: 1 s left
    await h.advance(1_000_000);
    expect(h.refreshes).toEqual([]);
    expect(h.pending()).toBe(0);
  });
});
