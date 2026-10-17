import { createGatewayClient } from "@loft/ts-client/gateway";
import { describe, expect, it } from "vitest";

import { fetchThumbnail } from "./thumbnails";

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

  it("throws on a transport failure so the query can retry", async () => {
    const client = clientReturning(envelope(503, "service_overloaded"));
    await expect(fetchThumbnail("assembly", ID, client)).rejects.toThrow(
      "could not be loaded",
    );
  });
});
