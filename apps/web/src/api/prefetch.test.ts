import { createGatewayClient } from "@loft/ts-client/gateway";
import { describe, expect, it } from "vitest";

import {
  cancelPrefetch,
  prefetchPrefix,
  type PrefetchRequest,
} from "./prefetch";

const INTENT: PrefetchRequest = {
  ticket: "feature_edit:part-1:feature-9",
  part_id: "00000000-0000-0000-0000-000000000001",
  feature_id: "00000000-0000-0000-0000-000000000009",
  kind: "feature_edit",
};

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function clientReturning(response: Response, seen?: Request[]) {
  return createGatewayClient({
    baseUrl: "http://gateway.test",
    fetch: (request: Request) => {
      seen?.push(request);
      return Promise.resolve(response);
    },
  });
}

describe("prefetchPrefix", () => {
  it("posts the intent and reports whether the worker took it", async () => {
    const seen: Request[] = [];
    const client = clientReturning(
      json({ ticket: INTENT.ticket, accepted: true }),
      seen,
    );
    await expect(prefetchPrefix(INTENT, client)).resolves.toBe(true);
    expect(seen[0]?.url).toBe("http://gateway.test/api/v1/geometry/prefetch");
  });

  it("is silent about every failure, because a cold rebuild is the only cost", async () => {
    // A prefetch that reported errors would be a UI that interrupts you about
    // an optimisation. 429 (rate limited), 502 (worker down) and a dead network
    // are all the same outcome: the next rebuild is as slow as it always was.
    const rateLimited = clientReturning(
      json({ error: { code: "rate_limited" } }, 429),
    );
    await expect(prefetchPrefix(INTENT, rateLimited)).resolves.toBe(false);

    const offline = createGatewayClient({
      baseUrl: "http://gateway.test",
      fetch: () => Promise.reject(new TypeError("Failed to fetch")),
    });
    await expect(prefetchPrefix(INTENT, offline)).resolves.toBe(false);
  });

  it("hands the app a boolean and nothing else, whatever the server says", async () => {
    // The load-bearing property, from the client's side: a warm is not an
    // answer. Even if a worker started attaching geometry to the reply, there
    // is one value this seam can return and it is a scheduling verdict — the
    // app has no path by which a speculative body could reach the viewport.
    const client = clientReturning(
      json({
        ticket: INTENT.ticket,
        accepted: true,
        mesh_glb_id: "sha256:beef",
      }),
    );
    await expect(prefetchPrefix(INTENT, client)).resolves.toBe(true);
  });
});

describe("cancelPrefetch", () => {
  it("posts the ticket the client chose", async () => {
    const seen: Request[] = [];
    const client = clientReturning(
      json({ ticket: INTENT.ticket, accepted: true }),
      seen,
    );
    await expect(cancelPrefetch(INTENT.ticket, client)).resolves.toBe(true);
    expect(seen[0]?.url).toBe(
      "http://gateway.test/api/v1/geometry/prefetch/cancel",
    );
    await expect(seen[0]?.json()).resolves.toEqual({ ticket: INTENT.ticket });
  });

  it("never throws when the cancel itself fails", async () => {
    const offline = createGatewayClient({
      baseUrl: "http://gateway.test",
      fetch: () => Promise.reject(new TypeError("Failed to fetch")),
    });
    await expect(cancelPrefetch("t", offline)).resolves.toBe(false);
  });
});
