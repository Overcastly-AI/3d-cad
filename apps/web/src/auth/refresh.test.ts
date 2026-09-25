import { createGatewayClient } from "@loft/ts-client/gateway";
import { describe, expect, it } from "vitest";

import {
  createRefresher,
  requestRefresh,
  tokenTimes,
  type RefreshOutcome,
} from "./refresh";
import type { SessionUser } from "./session";
import { fakeJwt } from "./testing";

const USER: SessionUser = {
  id: "6f2f0e6a-9c1e-4be5-9d3e-6a1c76a3c001",
  email: "alice@example.com",
  created_at: "2026-07-10T12:00:00Z",
};

function clientAnswering(answer: () => Promise<Response>) {
  const seen: Request[] = [];
  const client = createGatewayClient({
    baseUrl: "http://gateway.test",
    fetch: async (request) => {
      seen.push(request);
      return answer();
    },
  });
  return { client, seen };
}

/**
 * The fake network's in-flight requests, held from MODULE scope the way a
 * real network stack holds its sockets. A Request follows its caller's
 * signal only weakly (undici), and a stalled fake fetch is otherwise
 * reachable from nothing but that weak link, so the whole pending call can be
 * garbage-collected mid-test and the timeout never fires. Measured: with the
 * array inside the test it hung every time, and it passed whenever anything
 * else happened to keep the test's frame reachable.
 */
const inFlight: Request[] = [];

describe("requestRefresh", () => {
  it("200 is a new access token for the same user", async () => {
    const { client, seen } = clientAnswering(async () =>
      Response.json({
        user: USER,
        access_token: "tok-new",
        token_type: "bearer",
        expires_in: 3600,
      }),
    );
    const outcome = await requestRefresh(client);
    expect(outcome).toEqual({
      kind: "refreshed",
      token: "tok-new",
      user: USER,
    });
    expect(seen[0]?.method).toBe("POST");
    expect(new URL(seen[0]?.url ?? "").pathname).toBe("/api/v1/auth/refresh");
  });

  it("401 session_mismatch means the cookie is another user's now", async () => {
    const { client } = clientAnswering(async () =>
      Response.json(
        { error: { code: "session_mismatch", message: "x", details: null } },
        { status: 401 },
      ),
    );
    expect(await requestRefresh(client)).toEqual({ kind: "switched" });
  });

  it("401 means the session is over", async () => {
    const { client } = clientAnswering(async () =>
      Response.json(
        { error: { code: "invalid_token", message: "x", details: null } },
        { status: 401 },
      ),
    );
    expect(await requestRefresh(client)).toEqual({ kind: "rejected" });
  });

  it("a refresh that never answers gives up as 'unavailable' (review N4)", async () => {
    // Hangs until the request is aborted, as a stalled network would.
    const client = createGatewayClient({
      baseUrl: "http://gateway.test",
      fetch: (request) => {
        inFlight.push(request);
        return new Promise<Response>((_, reject) => {
          request.signal.addEventListener("abort", () =>
            reject(request.signal.reason as Error),
          );
        });
      },
    });
    const started = Date.now();
    expect(await requestRefresh(client, 30)).toEqual({ kind: "unavailable" });
    expect(Date.now() - started).toBeLessThan(5_000);
  });

  it.each([
    ["a 502", async () => new Response("bad gateway", { status: 502 })],
    ["a 429", async () => new Response("slow down", { status: 429 })],
    [
      "a network failure",
      async (): Promise<Response> => {
        throw new TypeError("Failed to fetch");
      },
    ],
  ])("%s is 'unavailable', never a sign-out", async (_label, answer) => {
    const { client } = clientAnswering(answer);
    expect(await requestRefresh(client)).toEqual({ kind: "unavailable" });
  });
});

describe("createRefresher", () => {
  function harness(outcome: RefreshOutcome) {
    const calls = { requests: 0, refreshed: [] as string[], rejected: 0 };
    let release: () => void = () => undefined;
    const refresher = createRefresher({
      request: () => {
        calls.requests += 1;
        return new Promise((resolve) => {
          release = () => resolve(outcome);
        });
      },
      onRefreshed: (token) => calls.refreshed.push(token),
      onRejected: () => {
        calls.rejected += 1;
      },
    });
    return { refresher, calls, release: () => release() };
  }

  it("single flight: concurrent callers share one request and one answer", async () => {
    const { refresher, calls, release } = harness({
      kind: "refreshed",
      token: "tok-new",
      user: USER,
    });
    const a = refresher.refresh();
    const b = refresher.refresh();
    release();
    expect(await a).toEqual(await b);
    expect(calls.requests).toBe(1);
    expect(calls.refreshed).toEqual(["tok-new"]);
    // …and a later refresh is a new request, not the old answer.
    const c = refresher.refresh();
    release();
    await c;
    expect(calls.requests).toBe(2);
  });

  it("rejected ends the session; unavailable does not", async () => {
    const rejected = harness({ kind: "rejected" });
    const pending = rejected.refresher.refresh();
    rejected.release();
    await pending;
    expect(rejected.calls.rejected).toBe(1);

    const unavailable = harness({ kind: "unavailable" });
    const again = unavailable.refresher.refresh();
    unavailable.release();
    await again;
    expect(unavailable.calls.rejected).toBe(0);
    expect(unavailable.calls.refreshed).toEqual([]);
  });

  it("a renewal that comes back as a different user is not adopted", async () => {
    const calls = { refreshed: 0, switched: 0, rejected: 0 };
    const refresher = createRefresher({
      request: async () => ({
        kind: "refreshed",
        token: "tok-y",
        user: { ...USER, id: "user-y" },
      }),
      currentUserId: () => USER.id,
      onRefreshed: () => {
        calls.refreshed += 1;
      },
      onRejected: () => {
        calls.rejected += 1;
      },
      onSwitched: () => {
        calls.switched += 1;
      },
    });
    expect(await refresher.refresh()).toEqual({ kind: "switched" });
    expect(calls).toEqual({ refreshed: 0, switched: 1, rejected: 0 });
  });

  it("the request runs inside the lock", async () => {
    const order: string[] = [];
    const refresher = createRefresher({
      request: async () => {
        order.push("request");
        return { kind: "unavailable" };
      },
      lock: async (task) => {
        order.push("acquire");
        const result = await task();
        order.push("release");
        return result;
      },
      onRefreshed: () => undefined,
      onRejected: () => undefined,
    });
    await refresher.refresh();
    expect(order).toEqual(["acquire", "request", "release"]);
  });
});

describe("tokenTimes", () => {
  it("reads iat/exp as epoch ms", () => {
    expect(tokenTimes(fakeJwt({ iat: 1000, exp: 4600 }))).toEqual({
      issuedAt: 1_000_000,
      expiresAt: 4_600_000,
    });
  });

  it("is null for anything it cannot read", () => {
    expect(tokenTimes("not-a-jwt")).toBeNull();
    expect(tokenTimes("a.%%%.c")).toBeNull();
    expect(tokenTimes(fakeJwt({ iat: 1000 }))).toBeNull();
  });
});
