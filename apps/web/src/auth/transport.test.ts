import { createGatewayClient } from "@loft/ts-client/gateway";
import { describe, expect, it } from "vitest";

import { createRefresher, type RefreshOutcome } from "./refresh";
import type { SessionUser } from "./session";
import { createAuthMiddleware, type SessionTransport } from "./transport";

const USER: SessionUser = {
  id: "6f2f0e6a-9c1e-4be5-9d3e-6a1c76a3c001",
  email: "alice@example.com",
  created_at: "2026-07-10T12:00:00Z",
};

function envelope401(code: string): Response {
  return new Response(
    JSON.stringify({
      error: { code, message: "Invalid or expired token.", details: null },
    }),
    { status: 401, headers: { "Content-Type": "application/json" } },
  );
}

/**
 * A session whose refresh answers with *outcome* (counting calls). *during*
 * runs inside the refresh, to change the world while it is in flight.
 */
function session(
  token: string | null,
  outcome: RefreshOutcome = { kind: "rejected" },
  during: (state: { userId: string | null }) => void = () => undefined,
) {
  const calls = { expired: 0, refreshed: 0 };
  let current = token;
  const state = { userId: token === null ? null : USER.id };
  const transport: SessionTransport = {
    getToken: () => current,
    getUserId: () => state.userId,
    refresh: async () => {
      calls.refreshed += 1;
      during(state);
      if (outcome.kind === "refreshed") current = outcome.token;
      return outcome;
    },
    expire: () => {
      calls.expired += 1;
      current = null;
    },
  };
  return { transport, calls };
}

/**
 * A scripted gateway: each request is recorded (with its bearer and body, read
 * at send time) and answered by the next scripted response.
 */
function scriptedFetch(responses: Response[]) {
  const sent: { url: string; bearer: string | null; body: string }[] = [];
  // A `function`, not an arrow, so it can check its receiver the way the
  // browser's fetch does: called as a METHOD of some other object it throws
  // "Illegal invocation" in Chromium. Node's fetch does not check, which is
  // how `options.fetch(request)` once passed here and failed in the browser.
  const fetch = async function (
    this: unknown,
    request: Request,
  ): Promise<Response> {
    if (this !== undefined && this !== globalThis) {
      throw new TypeError("Illegal invocation");
    }
    sent.push({
      url: new URL(request.url).pathname,
      bearer: request.headers.get("Authorization"),
      body: await request.text(),
    });
    const next = responses.shift();
    if (next === undefined) throw new Error("unscripted request");
    return next;
  };
  return { fetch, sent };
}

/**
 * The REAL client with the middleware installed — so the tests exercise
 * openapi-fetch's own request/response plumbing (the body is consumed by the
 * first send; the Request object onResponse sees), not a hand-rolled copy of it.
 */
function clientWith(transport: SessionTransport, responses: Response[]) {
  const script = scriptedFetch(responses);
  const client = createGatewayClient({
    baseUrl: "http://gateway.test",
    fetch: script.fetch,
  });
  client.use(createAuthMiddleware(transport));
  return { client, sent: script.sent };
}

const PART = "0b7d4b5e-1111-4222-8333-444455556666";

async function createFeature(client: ReturnType<typeof createGatewayClient>) {
  return client.POST("/api/v1/parts/{part_id}/features", {
    params: { path: { part_id: PART } },
    body: {
      name: "Chamfer1",
      feature: {
        type: "chamfer",
        version: 1,
        params: { distance_mm: 0.5, edges: { kind: "all_edges" } },
      },
      expected_tree_version: 7,
    } as never,
  });
}

describe("createAuthMiddleware", () => {
  it("attaches the bearer header while signed in", async () => {
    const { transport } = session("tok-abc");
    const { client, sent } = clientWith(transport, [
      new Response(JSON.stringify(USER), { status: 200 }),
    ]);
    await client.GET("/api/v1/auth/me");
    expect(sent[0]?.bearer).toBe("Bearer tok-abc");
  });

  it("leaves requests untouched while signed out", async () => {
    const { transport } = session(null);
    const { client, sent } = clientWith(transport, [
      new Response("{}", { status: 200 }),
    ]);
    await client.GET("/api/v1/auth/me");
    expect(sent[0]?.bearer).toBeNull();
  });

  it("an expired token mid-command: refresh once, resend the SAME request once, and the command commits", async () => {
    const { transport, calls } = session("tok-stale", {
      kind: "refreshed",
      token: "tok-fresh",
      user: USER,
    });
    const created = { feature: { id: "f-1" }, tree_version: 8 };
    const { client, sent } = clientWith(transport, [
      envelope401("invalid_token"),
      new Response(JSON.stringify(created), {
        status: 201,
        headers: { "Content-Type": "application/json" },
      }),
    ]);

    const { data, error, response } = await createFeature(client);

    // The caller sees the retried answer and nothing of the gap.
    expect(error).toBeUndefined();
    expect(response.status).toBe(201);
    expect(data).toEqual(created);
    expect(calls).toEqual({ refreshed: 1, expired: 0 });
    // Exactly two sends of the same call: stale token, then fresh token.
    expect(sent.map((s) => s.url)).toEqual([
      `/api/v1/parts/${PART}/features`,
      `/api/v1/parts/${PART}/features`,
    ]);
    expect(sent.map((s) => s.bearer)).toEqual([
      "Bearer tok-stale",
      "Bearer tok-fresh",
    ]);
    // The body survived the first send: the retry carries the whole command.
    expect(sent[1]?.body).toBe(sent[0]?.body);
    expect(JSON.parse(sent[1]?.body ?? "null")).toMatchObject({
      name: "Chamfer1",
      expected_tree_version: 7,
    });
  });

  it("retries ONCE: a second invalid_token after a fresh token ends the session, no loop", async () => {
    const { transport, calls } = session("tok-stale", {
      kind: "refreshed",
      token: "tok-fresh",
      user: USER,
    });
    const { client, sent } = clientWith(transport, [
      envelope401("invalid_token"),
      envelope401("invalid_token"),
    ]);
    const { response } = await createFeature(client);
    expect(response.status).toBe(401);
    expect(sent).toHaveLength(2);
    expect(calls).toEqual({ refreshed: 1, expired: 1 });
  });

  it("a refused refresh does not resend; the caller gets the original 401", async () => {
    // (The refresher ends the session on "rejected" — see refresh.test.ts.)
    const { transport, calls } = session("tok-stale", { kind: "rejected" });
    const { client, sent } = clientWith(transport, [
      envelope401("invalid_token"),
    ]);
    const { response } = await createFeature(client);
    expect(response.status).toBe(401);
    expect(sent).toHaveLength(1);
    expect(calls.refreshed).toBe(1);
  });

  it("a renewal that turns out to be SOMEONE ELSE's is never replayed (shared browser)", async () => {
    const { transport, calls } = session("tok-x", { kind: "switched" });
    const { client, sent } = clientWith(transport, [
      envelope401("invalid_token"),
    ]);
    const { response } = await createFeature(client);
    expect(response.status).toBe(401);
    expect(sent).toHaveLength(1); // X's command is not resent as anybody
    expect(calls.refreshed).toBe(1);
  });

  it("a request sent as X is not resent after the tab became Y, even on a good renewal", async () => {
    const { transport } = session(
      "tok-x",
      { kind: "refreshed", token: "tok-y", user: { ...USER, id: "user-y" } },
      (state) => {
        state.userId = "user-y"; // Y signed in while X's request was out
      },
    );
    const { client, sent } = clientWith(transport, [
      envelope401("invalid_token"),
    ]);
    const { response } = await createFeature(client);
    expect(response.status).toBe(401);
    expect(sent.map((s) => s.bearer)).toEqual(["Bearer tok-x"]);
  });

  it("an unreachable refresh keeps the session: no resend, no expiry", async () => {
    const { transport, calls } = session("tok-stale", { kind: "unavailable" });
    const { client, sent } = clientWith(transport, [
      envelope401("invalid_token"),
    ]);
    const { response } = await createFeature(client);
    expect(response.status).toBe(401);
    expect(sent).toHaveLength(1);
    expect(calls).toEqual({ refreshed: 1, expired: 0 });
  });

  it("a request that raced a refresh is resent with the new token without refreshing again", async () => {
    const { transport, calls } = session("tok-stale", {
      kind: "refreshed",
      token: "tok-fresh",
      user: USER,
    });
    const { client, sent } = clientWith(transport, [
      envelope401("invalid_token"),
      new Response("{}", { status: 200 }),
    ]);
    // Another request's refresh lands while this one is in flight.
    const pending = client.GET("/api/v1/auth/me");
    await transport.refresh();
    await pending;
    expect(calls.refreshed).toBe(1);
    expect(sent.map((s) => s.bearer)).toEqual([
      "Bearer tok-stale",
      "Bearer tok-fresh",
    ]);
  });

  it("concurrent 401s share ONE refresh (a spent cookie is never presented twice)", async () => {
    let requests = 0;
    let current: string | null = "tok-stale";
    let release: (outcome: RefreshOutcome) => void = () => undefined;
    const refresher = createRefresher({
      request: () => {
        requests += 1;
        return new Promise<RefreshOutcome>((resolve) => {
          release = resolve;
        });
      },
      onRefreshed: (token) => {
        current = token;
      },
      onRejected: () => undefined,
    });
    const transport: SessionTransport = {
      getToken: () => current,
      getUserId: () => USER.id,
      refresh: () => refresher.refresh(),
      expire: () => undefined,
    };
    const { client, sent } = clientWith(transport, [
      envelope401("invalid_token"),
      envelope401("invalid_token"),
      new Response("{}", { status: 200 }),
      new Response("{}", { status: 200 }),
    ]);
    const both = Promise.all([
      client.GET("/api/v1/auth/me"),
      client.GET("/api/v1/auth/me"),
    ]);
    await new Promise((resolve) => setTimeout(resolve, 0));
    release({ kind: "refreshed", token: "tok-fresh", user: USER });
    const results = await both;
    expect(requests).toBe(1);
    expect(results.map((r) => r.response.status)).toEqual([200, 200]);
    expect(sent.slice(2).map((s) => s.bearer)).toEqual([
      "Bearer tok-fresh",
      "Bearer tok-fresh",
    ]);
  });

  it("never renews on the session routes' own 401s (login, refresh)", async () => {
    const { transport, calls } = session("tok-live", {
      kind: "refreshed",
      token: "tok-fresh",
      user: USER,
    });
    const { client } = clientWith(transport, [
      envelope401("invalid_credentials"),
      envelope401("invalid_token"),
    ]);
    await client.POST("/api/v1/auth/login", {
      body: { email: "a@example.com", password: "whatever-123" },
    });
    await client.POST("/api/v1/auth/refresh");
    expect(calls).toEqual({ refreshed: 0, expired: 0 });
  });

  it("does not renew on non-401s, other 401 codes, or a non-JSON 401", async () => {
    const { transport, calls } = session("tok-live", {
      kind: "refreshed",
      token: "tok-fresh",
      user: USER,
    });
    const { client } = clientWith(transport, [
      new Response("{}", { status: 200 }),
      envelope401("unauthorized"),
      new Response("plain text", { status: 401 }),
    ]);
    await client.GET("/api/v1/auth/me");
    await client.GET("/api/v1/auth/me");
    await client.GET("/api/v1/auth/me");
    expect(calls).toEqual({ refreshed: 0, expired: 0 });
  });
});
