import { createGatewayClient } from "@loft/ts-client/gateway";
import { describe, expect, it } from "vitest";

import {
  fetchThumbnail,
  MAX_IN_FLIGHT,
  ThumbnailBusyError,
} from "./thumbnails";

/** Typed client whose transport records the URL and returns a canned response. */
function clientReturning(response: Response, seen: string[] = []) {
  return createGatewayClient({
    baseUrl: "http://gateway.test",
    fetch: (input: Request) => {
      seen.push(new URL(input.url).pathname);
      return Promise.resolve(response);
    },
  });
}

function envelope(status: number, code: string): Response {
  return new Response(JSON.stringify({ error: { code, message: code } }), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const ID = "6f3d1e0a-0000-4000-8000-000000000001";

describe("fetchThumbnail", () => {
  it("returns the PNG as a blob from the kind's own route", async () => {
    const png = new Uint8Array([0x89, 0x50, 0x4e, 0x47]);
    for (const [kind, path] of [
      ["part", `/api/v1/parts/${ID}/thumbnail`],
      ["assembly", `/api/v1/assemblies/${ID}/thumbnail`],
      ["drawing", `/api/v1/drawings/${ID}/thumbnail`],
    ] as const) {
      const seen: string[] = [];
      const client = clientReturning(
        new Response(png, {
          status: 200,
          headers: { "Content-Type": "image/png" },
        }),
        seen,
      );
      const result = await fetchThumbnail(kind, ID, client);
      expect(seen).toEqual([path]);
      expect(result.kind).toBe("image");
      if (result.kind === "image") {
        expect(new Uint8Array(await result.blob.arrayBuffer())).toEqual(png);
      }
    }
  });

  it("maps thumbnail_failed to the failed placeholder", async () => {
    const client = clientReturning(envelope(422, "thumbnail_failed"));
    await expect(fetchThumbnail("part", ID, client)).resolves.toEqual({
      kind: "unavailable",
      reason: "failed",
    });
  });

  it("maps any other 422 to the empty placeholder", async () => {
    const client = clientReturning(envelope(422, "thumbnail_empty"));
    await expect(fetchThumbnail("drawing", ID, client)).resolves.toEqual({
      kind: "unavailable",
      reason: "empty",
    });
  });

  it("turns a 503 into a busy error carrying Retry-After", async () => {
    const busy = new Response(
      JSON.stringify({
        error: { code: "service_overloaded", message: "busy" },
      }),
      {
        status: 503,
        headers: { "Content-Type": "application/json", "Retry-After": "3" },
      },
    );
    const error: unknown = await fetchThumbnail(
      "part",
      ID,
      clientReturning(busy),
    ).catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(ThumbnailBusyError);
    expect((error as ThumbnailBusyError).retryAfterMs).toBe(3000);
  });

  it("keeps at most MAX_IN_FLIGHT requests in flight", async () => {
    let running = 0;
    let peak = 0;
    const releases: Array<() => void> = [];
    const client = createGatewayClient({
      baseUrl: "http://gateway.test",
      fetch: async () => {
        running += 1;
        peak = Math.max(peak, running);
        await new Promise<void>((resolve) => releases.push(resolve));
        running -= 1;
        return new Response(new Uint8Array([1]), {
          status: 200,
          headers: { "Content-Type": "image/png" },
        });
      },
    });
    const all = Promise.all(
      Array.from({ length: 12 }, () => fetchThumbnail("part", ID, client)),
    );
    while (releases.length > 0 || running > 0 || peak === 0) {
      await new Promise((resolve) => setTimeout(resolve, 1));
      releases.shift()?.();
    }
    await all;
    expect(peak).toBe(MAX_IN_FLIGHT);
  });

  it("throws on a transport failure so the query can retry", async () => {
    const client = clientReturning(envelope(502, "upstream_unavailable"));
    await expect(fetchThumbnail("assembly", ID, client)).rejects.toThrow(
      "could not be loaded",
    );
  });
});
