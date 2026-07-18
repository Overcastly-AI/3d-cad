import { describe, expect, it } from "vitest";

import { createAuthMiddleware, type SessionTransport } from "./transport";

function session(token: string | null) {
  const calls = { expired: 0 };
  const transport: SessionTransport = {
    getToken: () => token,
    expire: () => {
      calls.expired += 1;
    },
  };
  return { transport, calls };
}

function envelope401(code: string): Response {
  return new Response(
    JSON.stringify({
      error: { code, message: "Invalid or expired token.", details: null },
    }),
    { status: 401, headers: { "Content-Type": "application/json" } },
  );
}

/** Minimal invocation of the middleware hooks (openapi-fetch calls these). */
type OnRequest = (ctx: { request: Request }) => Promise<Request | undefined>;
type OnResponse = (ctx: {
  response: Response;
}) => Promise<Response | undefined>;

describe("createAuthMiddleware", () => {
  it("attaches the bearer header while signed in", async () => {
    const { transport } = session("tok-abc");
    const middleware = createAuthMiddleware(transport);
    const request = new Request("http://gateway.test/api/v1/auth/me");
    const out = await (middleware.onRequest as OnRequest)({ request });
    expect(out?.headers.get("Authorization")).toBe("Bearer tok-abc");
  });

  it("leaves requests untouched while signed out", async () => {
    const { transport } = session(null);
    const middleware = createAuthMiddleware(transport);
    const request = new Request("http://gateway.test/api/v1/auth/login");
    const out = await (middleware.onRequest as OnRequest)({ request });
    expect(out?.headers.get("Authorization")).toBeNull();
  });

  it("expires the session on a 401 invalid_token envelope", async () => {
    const { transport, calls } = session("tok-stale");
    const middleware = createAuthMiddleware(transport);
    const out = await (middleware.onResponse as OnResponse)({
      response: envelope401("invalid_token"),
    });
    expect(calls.expired).toBe(1);
    // The response itself passes through so callers still see the failure.
    expect(out?.status).toBe(401);
    expect(await out?.json()).toMatchObject({
      error: { code: "invalid_token" },
    });
  });

  it("does NOT expire on a login invalid_credentials 401", async () => {
    const { transport, calls } = session(null);
    const middleware = createAuthMiddleware(transport);
    await (middleware.onResponse as OnResponse)({
      response: envelope401("invalid_credentials"),
    });
    expect(calls.expired).toBe(0);
  });

  it("does NOT expire on non-401 responses", async () => {
    const { transport, calls } = session("tok-live");
    const middleware = createAuthMiddleware(transport);
    await (middleware.onResponse as OnResponse)({
      response: new Response("{}", { status: 200 }),
    });
    expect(calls.expired).toBe(0);
  });

  it("tolerates a non-JSON 401 without expiring or throwing", async () => {
    const { transport, calls } = session("tok-live");
    const middleware = createAuthMiddleware(transport);
    await (middleware.onResponse as OnResponse)({
      response: new Response("plain text", { status: 401 }),
    });
    expect(calls.expired).toBe(0);
  });
});
